"""Step 3 of the loop: paste the copied bits, get the ASCII back.

Usage
-----
  1. open portrait_binary.txt
  2. select all, copy
  3. paste into pasted.txt
  4. python3 decrypt_ascii.py pasted.txt        (or just: python3 decrypt_ascii.py && paste)

Anything that is not 0 or 1 is ignored, so the portrait's layout spaces do not
matter -- only the order of the bits does.
"""
import hashlib
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "pasted.txt"
try:
    text = open(path).read()
except FileNotFoundError:
    print(f"paste the copied art into {path} first", file=sys.stderr)
    raise SystemExit(1)

bits = "".join(ch for ch in text if ch in "01")
bits = bits[:len(bits) - len(bits) % 8]
message = bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)).decode("ascii", "replace")

print(f"bits  : {len(bits)}")
print(f"bytes : {len(bits) // 8}")
print(f"sha   : {hashlib.sha256(bits.encode()).hexdigest()[:16]}")
print("-" * 60)
print(message)
open("decoded_message.txt", "w").write(message + "\n")
print("-" * 60)
print("saved -> decoded_message.txt")
