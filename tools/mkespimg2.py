import sys
from pyfatfs.PyFat import PyFat
from pyfatfs.PyFatFS import PyFatFS

img, size_mb, loader, payload = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
size = size_mb * 1024 * 1024
with open(img, 'wb') as f:
    f.truncate(size)
pf = PyFat()
pf.mkfs(img, PyFat.FAT_TYPE_FAT32, size=size, label='HAKIOS ESP')
pf.close()
fs = PyFatFS(img)
fs.makedirs('/EFI/BOOT')
fs.makedirs('/EFI/HAKIOS')
fs.setbytes('/EFI/BOOT/BOOTAA64.EFI', open(loader, 'rb').read())
fs.setbytes('/EFI/HAKIOS/payload.bin', open(payload, 'rb').read())
fs.close()
print('built', img)
fs = PyFatFS(img, read_only=True)
for p in ['/EFI', '/EFI/BOOT', '/EFI/HAKIOS', '/EFI/BOOT/BOOTAA64.EFI', '/EFI/HAKIOS/payload.bin']:
    info = fs.getinfo(p)
    print(' ', p, info.size if info.size is not None else '<dir>')
fs.close()
