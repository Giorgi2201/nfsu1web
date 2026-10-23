#!/usr/bin/env python3
"""Execute cached game font header/stream upload code with a synthetic heap/COM.

Requires private emitted sources and a prepared language pack. Generated game
code is extracted only into a temporary local directory and is never tracked.
The actual language header callback, texture metadata setup, range linking and
D3D upload loops and JDLZ decompressor execute natively. File I/O is supplied
by the harness; there is no browser/GPU or complete async scheduler validation.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = {
    'sub_005460e0', 'sub_005453d0', 'sub_005457f0', 'sub_00545900',
    'sub_005459f0', 'sub_00407db0', 'sub_0058d190',
}
HARNESS = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
uint8_t *g_mem;
guest_fn_t g_dtab[DISPATCH_TEXT_SIZE];
static uint32_t heap=0x2800000, count, hd_count, mip_copies;
static uint32_t alloc(unsigned n) {
    uint32_t p=heap; heap=(heap+n+127)&~127u; assert(heap<0x7800000); return p;
}
static void ret(CPU*c,unsigned bytes) { POP32(c->eip); c->esp+=bytes; }
void sub_0067121a(CPU*c) { c->eax=alloc(MR32(c->esp+4)); ret(c,0); }
void sub_00671102(CPU*c) { ret(c,0); }
void sub_00565da0(CPU*c) { ret(c,0); }
void sub_00447bb0(CPU*c) { ret(c,0); }
void sub_00565810(CPU*c) { abort(); }
void sub_0053e400(CPU*c) { c->eax=0; ret(c,0); }
void sub_0040caa0(CPU*c) { ret(c,0); }
void sub_004029a0(CPU*c) { ret(c,0); }
void sub_004f46c0(CPU*c) { ret(c,0); }
void sub_00408010(CPU*c) { abort(); }
void dispatch_tail(CPU*c) { abort(); }
void dispatch_indirect(CPU*c,uint32_t target) {
    if(target==0xf0000001u) {
        unsigned w=MR32(c->esp+8),h=MR32(c->esp+12),m=MR32(c->esp+16);
        unsigned fmt=MR32(c->esp+24),pp=MR32(c->esp+32),key=MR32(c->esi+0x24);
        uint32_t tex=alloc(64),vt=alloc(128);
        MR32(tex)=vt; MR32(tex+4)=w; MR32(tex+8)=h; MR32(tex+12)=m;
        MR32(tex+16)=fmt; MR32(tex+20)=MR32(c->esi+0x70);
        MR32(vt+0x4c)=0xf0000002; MR32(vt+0x50)=0xf0000003; MR32(pp)=tex;
        count++;
        unsigned expected=key==0x5b9d84db?1024:key==0x9583aa1a?2048:key==0xbbba71c2?512:0;
        if(expected && w==expected) { assert(h==expected && fmt==0x35545844); hd_count++; }
        printf("  upload hash=%08x %ux%u mips=%u format=%08x\n",key,w,h,m,fmt);
        c->eax=0; ret(c,36);
    } else if(target==0xf0000002u) {
        uint32_t tex=MR32(c->esp+4),level=MR32(c->esp+8),locked=MR32(c->esp+12);
        unsigned w=MR32(tex+4)>>level,h=MR32(tex+8)>>level,fmt=MR32(tex+16);
        unsigned size=w*h*(fmt==21?4:1),offset=0;
        for(unsigned i=0;i<level;i++) offset+=(MR32(tex+4)>>i)*(MR32(tex+8)>>i)*(fmt==21?4:1);
        MR32(locked)=w; MR32(locked+4)=alloc(size+128);
        MR32(tex+24)=MR32(locked+4); MR32(tex+28)=size; MR32(tex+32)=offset;
        c->eax=0; ret(c,20);
    } else if(target==0xf0000003u) {
        uint32_t tex=MR32(c->esp+4);
        assert(memcmp(g_mem+MR32(tex+24),g_mem+MR32(tex+20)+MR32(tex+32),MR32(tex+28))==0);
        mip_copies++; c->eax=0; ret(c,8);
    } else { fprintf(stderr,"unexpected COM target %08x\n",target); abort(); }
}
/* Compare the game's codec with an independent decoder at the file boundary. */
static uint32_t decode(uint32_t source,unsigned size) {
    assert(MR32(source)==0x5a4c444a && MR32(source+12)==size);
    unsigned length=MR32(source+8),out=alloc(length),written=0,pos=source+16;
    unsigned bits=1,modes=1;
    while(written<length) {
        if(bits==1) bits=MR8(pos++)|256;
        if(modes==1) modes=MR8(pos++)|256;
        if(bits&1) {
            unsigned a=MR8(pos++),b=MR8(pos++),distance,n;
            if(modes&1) { distance=(a&15)+1; n=((a&240)<<4)+b+3; }
            else { distance=((a&224)<<3)+b+17; n=(a&31)+3; }
            assert(distance<=written && written+n<=length);
            while(n--) { MR8(out+written)=MR8(out+written-distance); written++; }
            modes>>=1;
        } else { MR8(out+written++)=MR8(pos++); }
        bits>>=1; assert(pos<=source+size);
    }
    uint32_t actual=alloc(length+32);
    memset(g_mem+actual,0xcc,length+32);
    CPU cpu={0},*c=&cpu; c->esp=0x2600000; c->eax=actual; c->edx=source;
    PUSH32(0xdeadbeef); sub_0058d190(c);
    assert(c->esp==0x2600000 && c->eip==0xdeadbeef && c->eax==length);
    assert(c->edx>=source+size-2 && c->edx<=source+size);
    assert(memcmp(g_mem+out,g_mem+actual,length)==0);
    for(unsigned i=0;i<32;i++) assert(MR8(actual+length+i)==0xcc);
    return actual;
}
int main(int argc,char**argv) {
    assert(argc==3); g_mem=calloc(1,0x8000000);
    FILE*f=fopen(argv[1],"rb"); assert(f); fseek(f,0,SEEK_END);
    unsigned size=ftell(f); fseek(f,0,SEEK_SET); assert(size<0x1000000);
    const uint32_t base=0x1000000; assert(fread(g_mem+base,1,size,f)==size); fclose(f);
    MR32(0x740418)=MR32(0x74041c)=0x740418;
    CPU cpu={0},*c=&cpu; c->esp=0x2700000; c->fs_base=0x1000;
    uint32_t dev=alloc(128),vt=alloc(128); MR32(dev)=vt; MR32(vt+0x5c)=0xf0000001; MR32(0x73636c)=dev;
    uint32_t header=base+8;
    while(MR32(header)!=0xb3310000) { header+=MR32(header+4)+8; assert(header<base+size); }
    uint32_t context=alloc(64),file=alloc(256); MR32(context+4)=header; MR32(context+12)=file;
    PUSH32(context); PUSH32(0xdeadbeef); sub_005460e0(c); c->esp+=4;
    uint32_t table=MR32(context+16),entries=MR32(context+20),info=MR32(context+28);
    if(!table || entries!=8) { fprintf(stderr,"language header has no usable 8-entry texture stream table\n"); return 2; }
    uint32_t pack=MR32(info+0x70),records=MR32(pack+0x74);
    for(unsigned i=0;i<entries;i++) {
        uint32_t entry=table+20*i,key=MR32(entry),record=0;
        for(unsigned j=0;j<entries;j++) if(MR32(records+124*j+36)==key) record=records+124*j;
        assert(record && MR32(entry+4)+MR32(entry+8)<=size);
        uint32_t pixels=decode(base+MR32(entry+4),MR32(entry+8));
        assert(MR32(base+MR32(entry+4)+8)==MR32(record+56));
        PUSH32(MR32(record+56)); PUSH32(MR32(record+48)); PUSH32(pixels);
        c->eax=pack; PUSH32(0xdeadbeef); sub_005459f0(c);
    }
    assert(count==8 && hd_count==(unsigned)atoi(argv[2]));
    printf("font_container_smoke ok: actual language header/stream linking/JDLZ/upload loops, %u textures, %u HD fonts, %u exact mip copies\n",count,hd_count,mip_copies);
    return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gen', type=Path, default=ROOT / 'gen/nfsu1-current')
    parser.add_argument('--pack', type=Path, default=ROOT / 'work/mods/hd-fonts/data/Languages/LanguageTextures.bin')
    parser.add_argument('--expected-hd', type=int, default=3)
    args = parser.parse_args()
    bodies = {}
    for path in args.gen.glob('shard_*.c'):
        source = path.read_text()
        for name in FUNCTIONS - set(bodies):
            match = re.search(r'void ' + name + r'\(CPU \*restrict c\) \{.*?\n\}', source, re.S)
            if match:
                bodies[name] = match[0]
        if len(bodies) == len(FUNCTIONS):
            break
    if set(bodies) != FUNCTIONS:
        parser.error('Required cached emitted game functions are missing')
    calls = set().union(*(set(re.findall(r'(sub_[0-9a-f]+)\(c\)', body)) for body in bodies.values()))
    declarations = ''.join(f'void {name}(CPU *c);\n' for name in sorted(calls | FUNCTIONS))
    with tempfile.TemporaryDirectory(prefix='nfsu1-font-container-') as temporary:
        directory = Path(temporary)
        source = directory / 'smoke.c'
        source.write_text('#include "cpu.h"\n#include "nfsu1_fonts.h"\n' + declarations
                          + '\n'.join(bodies.values()) + HARNESS)
        executable = directory / 'smoke'
        subprocess.check_call(['cc', '-O0', '-I', str(ROOT / 'work/upstream/nfsu2-web/runtime'),
                               '-I', str(ROOT / 'runtime'), str(source), str(ROOT / 'runtime/nfsu1_fonts.c'),
                               '-o', str(executable)])
        subprocess.check_call([str(executable), str(args.pack.resolve()), str(args.expected_hd)], timeout=20)


if __name__ == '__main__':
    main()
