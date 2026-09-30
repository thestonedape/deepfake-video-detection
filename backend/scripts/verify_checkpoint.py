"""Resolve an unresolved Git LFS pointer at build time and verify the original checkpoint."""
import hashlib
from pathlib import Path
import urllib.request

SHA256 = '1bdb710834262826666c776e4a80662ae13c196c16a1eff9b16976ffa2abe178'
SIZE = 87272477
URL = ('https://media.githubusercontent.com/media/thestonedape/deepfake-video-detection/'
       'd9114da32494bb205a95c051d97486fcec1e7209/best_model.pt')


def verify(path):
    path = Path(path)
    with path.open('rb') as source:
        pointer = source.read(128).startswith(b'version https://git-lfs.github.com/spec/')
    temporary = path.with_suffix('.download')
    try:
        if pointer:
            urllib.request.urlretrieve(URL, temporary)
            candidate = temporary
        else:
            candidate = path
        with candidate.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        if candidate.stat().st_size != SIZE or digest != SHA256:
            raise RuntimeError('Checkpoint size/checksum does not match the verified original')
        if pointer:
            temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    verify('best_model.pt')
    print('Original checkpoint size and SHA-256 verified')
