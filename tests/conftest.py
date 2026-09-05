from pathlib import Path

import pytest


@pytest.fixture
def listing_text() -> str:
    return """ Volume in drive C has no label.
 Volume Serial Number is 1234-ABCD

 Directory of C:\\Users\\Alice

01/02/2024  03:04 PM    <DIR>          Documents
01/02/2024  03:05 PM             1,234 notes file.txt
               1 File(s)          1,234 bytes
               3 Dir(s)     10,000,000 bytes free

 Directory of C:\\Users\\Alice\\Documents

01/02/2024  15:06                 8 todo.txt
               1 File(s)              8 bytes
               2 Dir(s)     10,000,000 bytes free

     Total Files Listed:
               2 File(s)          1,242 bytes
               5 Dir(s)     10,000,000 bytes free
"""


@pytest.fixture
def listing_file(tmp_path: Path, listing_text: str) -> Path:
    path = tmp_path / "listing.txt"
    path.write_bytes(listing_text.encode())
    return path
