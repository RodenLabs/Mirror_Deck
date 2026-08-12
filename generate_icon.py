import struct, zlib

def create_ico():
    def make_png(size):
        w, h = size, size
        bg = (26, 26, 46, 255)
        phone = (78, 204, 163, 255)
        pixels = []
        cx, cy = w//2, h//2
        pw = max(2, w//4)
        ph = max(3, h//2)
        px1, py1 = cx-pw, cy-ph//2
        px2, py2 = cx+pw, cy+ph//2
        br = max(1, w//12)
        for y in range(h):
            row = []
            for x in range(w):
                in_phone = (px1+br<=x<=px2-br and py1<=y<=py2) or (px1<=x<=px2 and py1+br<=y<=py2-br)
                if in_phone:
                    row.extend(phone)
                else:
                    row.extend(bg)
            pixels.append(bytes(row))
        def chunk(name, data):
            c = name+data
            return struct.pack('>I',len(data))+c+struct.pack('>I',zlib.crc32(c)&0xffffffff)
        sig = b'\x89PNG\r\n\x1a\n'
        ihdr_d = struct.pack('>II',w,h)+bytes([8,6,0,0,0])
        ihdr = chunk(b'IHDR',ihdr_d)
        raw = b''
        for row in pixels:
            raw += b'\x00'+row
        idat = chunk(b'IDAT',zlib.compress(raw,9))
        iend = chunk(b'IEND',b'')
        return sig+ihdr+idat+iend
    sizes = [256,128,64,48,32,16]
    pngs = [(s,make_png(s)) for s in sizes]
    num = len(pngs)
    header = struct.pack('<HHH',0,1,num)
    offset = 6+num*16
    entries = b''
    for size,png in pngs:
        w_byte = 0 if size>=256 else size
        entries += struct.pack('<BBBBHHII',w_byte,w_byte,0,0,1,32,len(png),offset)
        offset += len(png)
    data = b''.join(p for _,p in pngs)
    ico = header+entries+data
    with open('icon.ico','wb') as f:
        f.write(ico)
    print(f'[OK] icon.ico generado ({len(ico)} bytes)')

if __name__ == '__main__':
    create_ico()
