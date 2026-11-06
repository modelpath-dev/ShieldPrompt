"""Security regression tests use synthetic data and offline fake NER backends."""
import pytest

from shieldprompt import Shield, Vault
from shieldprompt.detector.hybrid import HybridDetector
from shieldprompt.detector.regex_engine import Detection, RegexDetector, merge_overlaps
from shieldprompt.detector.ner_engine import NERDetector
from shieldprompt.detector.presidio_engine import PresidioDetector


def make_shield(entities):
    return Shield(entities=set(entities), use_ner=False, vault=Vault())


@pytest.mark.parametrize('text', [
    'before https://192.0.2.1/path after',
    'before https://test@example.com/192.0.2.1 after',
])
def test_overlapping_url_spans_roundtrip(text):
    shield = make_shield({'URL', 'IP_ADDRESS', 'EMAIL_ADDRESS'})
    masked = shield.mask(text)
    assert masked == 'before [URL_1] after'
    assert shield.unmask(masked) == text


def test_partial_overlap_union_preserves_all_sensitive_characters():
    merged = merge_overlaps('abcdefgh', [Detection('URL', 'abcd', 0, 4),
                                         Detection('PERSON', 'cdef', 2, 6)])
    assert len(merged) == 1
    assert (merged[0].start, merged[0].end, merged[0].value) == (0, 6, 'abcdef')


@pytest.mark.parametrize('key', [
    'sk-proj-' + 'aB1_' * 20 + '-end',
    'sk-svcacct-' + 'aB1_' * 20,
    'github_pat_' + 'abc123_' * 12,
    'ghp_' + 'a' * 36,
])
def test_modern_synthetic_credentials(key):
    shield = make_shield({'API_KEY'})
    masked = shield.mask('key=' + key)
    assert masked == 'key=[API_KEY_1]'
    assert shield.unmask(masked) == 'key=' + key


@pytest.mark.parametrize('text, value', [
    ('ligature ﬃ: alice@example.com', 'alice@example.com'),
    ('contact ali\u200bce@exam\u2060ple.com', 'ali\u200bce@exam\u2060ple.com'),
    ('contact ａｌｉｃｅ＠ｅｘａｍｐｌｅ．ｃｏｍ', 'ａｌｉｃｅ＠ｅｘａｍｐｌｅ．ｃｏｍ'),
    ('ﬃ contact alice@example.com\u200b\u200b', 'alice@example.com'),
])
def test_unicode_normalization_original_offsets(text, value):
    shield = make_shield({'EMAIL_ADDRESS'})
    masked = shield.mask(text)
    assert value not in masked
    assert shield.unmask(masked) == text
    assert value in shield.vault.mappings.values()


def test_normalized_card_validation():
    shield = make_shield({'CREDIT_CARD'})
    text = '４１１１\u200b１１１１\u200b１１１１\u200b１１１１'
    assert shield.mask(text) == '[CREDIT_CARD_1]'
    assert shield.unmask('[CREDIT_CARD_1]') == text


def test_empty_entity_selection_detects_nothing():
    text = 'alice@example.com 192.0.2.1'
    assert RegexDetector(set()).detect(text) == []
    assert HybridDetector(set()).detect(text) == []
    assert make_shield(set()).mask(text) == text


def test_ner_only_selection_does_not_enable_regex():
    assert HybridDetector({'PERSON'}, use_ner=False).detect('alice@example.com') == []


def test_requested_ner_initialization_fails_closed(monkeypatch):
    attempts = []
    def fail(self):
        attempts.append(type(self).__name__)
        raise ImportError('offline synthetic missing dependency')
    monkeypatch.setattr(PresidioDetector, '_load', fail)
    monkeypatch.setattr(NERDetector, '_load', fail)
    with pytest.raises(RuntimeError, match='no usable backend'):
        Shield(entities={'PERSON'})
    assert attempts == ['PresidioDetector', 'NERDetector']
    assert make_shield({'PERSON'}).mask('Synthetic Person') == 'Synthetic Person'


def test_ner_runtime_failure_fails_closed(monkeypatch):
    class BrokenNER:
        def detect(self, text):
            raise RuntimeError('synthetic inference failure')
    monkeypatch.setattr(HybridDetector, '_init_ner_backend', staticmethod(lambda **kw: BrokenNER()))
    shield = Shield(entities={'PERSON', 'EMAIL_ADDRESS'}, vault=Vault())
    with pytest.raises(RuntimeError, match='refusing'):
        shield.mask('Synthetic Person alice@example.com')
    assert shield.vault.mappings == {}


@pytest.mark.parametrize('entity,text', [('DATE_OF_BIRTH', '2000-01-02'), ('MONEY', '$123.45')])
def test_previously_unimplemented_entities(entity, text):
    shield = make_shield({entity})
    masked = shield.mask(text)
    assert text not in masked
    assert shield.unmask(masked) == text


def test_invalid_detector_span_fails_closed():
    with pytest.raises(ValueError, match='invalid source span'):
        merge_overlaps('abc', [Detection('PERSON', 'secret', 0, 10)])


def test_transformer_rejects_unsupported_entity_configuration(monkeypatch):
    import sys
    from types import SimpleNamespace
    fake_pipeline = SimpleNamespace(model=SimpleNamespace(
        config=SimpleNamespace(id2label={0: 'O', 1: 'B-PER', 2: 'I-PER'})))
    monkeypatch.setitem(sys.modules, 'transformers', SimpleNamespace(
        pipeline=lambda *args, **kwargs: fake_pipeline))
    detector = NERDetector(entities={'DATE'})
    with pytest.raises(RuntimeError, match='does not support'):
        detector._load()
    assert detector._pipeline is None


def test_missing_spacy_model_never_triggers_download(monkeypatch):
    import sys
    from types import SimpleNamespace
    def missing_model(name):
        raise OSError('synthetic missing model')
    monkeypatch.setitem(sys.modules, 'spacy', SimpleNamespace(load=missing_model))
    with pytest.raises(RuntimeError, match='Install it explicitly'):
        PresidioDetector()._ensure_spacy_model()


def test_presidio_explicit_configuration_keeps_default_organization(monkeypatch):
    """Exercise initialization without inheriting version-dependent ORG defaults."""
    import sys
    from types import SimpleNamespace
    configuration = {}

    class Provider:
        def __init__(self, nlp_configuration):
            configuration.update(nlp_configuration)

        def create_engine(self):
            return configuration['ner_model_configuration']

    class Analyzer:
        def __init__(self, nlp_engine, default_score_threshold):
            self.config = nlp_engine
            self.threshold = default_score_threshold

        def get_supported_entities(self, language):
            return set(self.config['model_to_presidio_entity_mapping'].values()) - set(
                self.config['labels_to_ignore'])

        def analyze(self, text, language):
            label = self.config['model_to_presidio_entity_mapping']['ORG']
            score = self.config['default_score']
            assert label not in self.config['low_score_entity_names']
            assert score >= self.threshold
            return [SimpleNamespace(entity_type=label, start=0, end=len(text), score=score)]

    monkeypatch.setitem(sys.modules, 'presidio_analyzer', SimpleNamespace(AnalyzerEngine=Analyzer))
    monkeypatch.setitem(sys.modules, 'presidio_analyzer.nlp_engine', SimpleNamespace(NlpEngineProvider=Provider))
    monkeypatch.setattr(PresidioDetector, '_ensure_spacy_model', lambda self: None)
    shield = Shield(vault=Vault())
    assert isinstance(shield._detector._ner, PresidioDetector)
    text = 'Synthetic Example Company'
    masked = shield.mask(text)
    assert masked == '[ORGANIZATION_1]'
    assert shield.unmask(masked) == text
