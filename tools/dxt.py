import struct, numpy as np
from PIL import Image
def c565(v):
    r=(v>>11)&31; g=(v>>5)&63; b=v&31
    return np.array([r*255//31, g*255//63, b*255//31],dtype=np.int32)
def decode_dxt5(data,w,h):
    out=np.zeros((h,w,4),np.uint8); i=0
    for by in range(0,h,4):
        for bx in range(0,w,4):
            blk=data[i:i+16]; i+=16
            a0,a1=blk[0],blk[1]; ab=int.from_bytes(blk[2:8],'little')
            al=[a0,a1]+([(a0*(7-k)+a1*k)//7 for k in range(1,7)] if a0>a1 else [(a0*(5-k)+a1*k)//5 for k in range(1,5)]+[0,255])
            c0,c1=struct.unpack_from('<HH',blk,8); cb=struct.unpack_from('<I',blk,12)[0]
            p0,p1=c565(c0),c565(c1); cols=[p0,p1,(2*p0+p1)//3,(p0+2*p1)//3]
            for py in range(4):
                for px in range(4):
                    k=py*4+px
                    out[by+py,bx+px,:3]=cols[(cb>>(2*k))&3]
                    out[by+py,bx+px,3]=al[(ab>>(3*k))&7]
    return out
if __name__=='__main__':
    import sys
    for name,w,h in [('small.xpr',128,128),('large.xpr',256,512)]:
        d=open(sys.argv[1]+'/'+name,'rb').read()[0x800:]
        img=decode_dxt5(d,w,h)
        Image.fromarray(img).save(f'/home/claude/work/{name}.png')
        # alpha-over-dark preview
        a=img[...,3:4]/255.0; bg=np.full_like(img[...,:3],40)
        prev=(img[...,:3]*a+bg*(1-a)).astype(np.uint8)
        Image.fromarray(prev).resize((w*3,h*3),Image.NEAREST).save(f'/home/claude/work/{name}_preview.png')
