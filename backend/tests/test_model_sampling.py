"""Runtime-dependent checks; intentionally separate from lightweight PR checks."""
from pathlib import Path
import pytest

pytest.importorskip('torch')
import cv2
import numpy as np
import torch
import model


@pytest.mark.parametrize('unseekable', [False, True])
def test_sampling_is_identical_and_retained_memory_is_bounded(monkeypatch, unseekable):
    rng = np.random.default_rng(930)
    # A 4K frame stresses retained memory; short clips also test duplicate padding.
    source = rng.integers(0, 256, (2160, 3840, 3), dtype=np.uint8)
    expected = model.preprocess_frame(source)
    opened = []

    class Capture:
        def __init__(self):
            self.index = 0
            self.seeking = False
            self.released = False
            opened.append(self)
        def isOpened(self): return True
        def get(self, prop): return 3
        def set(self, prop, index):
            self.seeking = True
            self.index = index
            return not unseekable
        def read(self):
            if (unseekable and self.seeking) or self.index >= 3:
                return False, None
            self.index += 1
            return True, source.copy()
        def release(self): self.released = True

    monkeypatch.setattr(cv2, 'VideoCapture', lambda path: Capture())
    frames, count = model.load_sampled_video_frames(Path('fixture.mp4'))
    assert count == 3 and len(frames) == 10
    assert sum(frame.nbytes for frame in frames) == 10 * 224 * 224 * 3
    assert all(capture.released for capture in opened)
    assert len(opened) == (2 if unseekable else 1)
    for frame in frames:
        assert torch.equal(model.preprocess_frame(frame), expected)


def test_resize_reordering_preserves_preprocessing_corpus():
    rng = np.random.default_rng(7300930)
    for index in range(50):
        height, width = [(64, 64), (480, 640), (224, 224), (320, 180), (720, 1280)][index % 5]
        frame = rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
        retained = cv2.resize(frame, (224, 224), interpolation=cv2.INTER_AREA)
        assert torch.equal(model.preprocess_frame(frame), model.preprocess_frame(retained))
