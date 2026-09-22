import struct

from classfox.microphone import EnergySegmenter


def test_energy_segmentation_bounds_silence_utterances_and_flushes_tail() -> None:
    segmenter = EnergySegmenter()
    silence, voice = b"\0\0" * 1600, struct.pack("<h", 3000) * 1600
    for _ in range(500):
        assert segmenter.feed(silence) == []
    assert segmenter.flush() == []
    assert segmenter.feed(voice) == []
    assert segmenter.flush() == [voice]
    results = []
    for _ in range(205):
        results.extend(segmenter.feed(voice))
    results.extend(segmenter.flush())
    assert [len(pcm) for pcm in results] == [320000, 320000, 16000]


def test_silence_finalizes_utterance_and_next_one_keeps_preroll() -> None:
    segmenter = EnergySegmenter()
    silence, voice = b"\0\0" * 1600, struct.pack("<h", 3000) * 1600
    segmenter.feed(silence)
    segmenter.feed(voice)
    result = []
    for _ in range(6):
        result.extend(segmenter.feed(silence))
    assert result == [silence + voice + silence * 6]
    assert segmenter.flush() == []
