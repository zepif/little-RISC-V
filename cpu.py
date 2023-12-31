#!/usr/bin/env python3
import os
from elftools.elf.elffile import ELFFile
from elftools.common.exceptions import ELFError
import struct
import binascii
import glob

regnames = \
    ['x0', 'ra', 'sp', 'gp', 'tp'] + ['t%d'%i for i in range(0, 3)] +\
    ['s0', 's1'] + ['a%d'%i for i in range(0, 8)] +\
    ['s%d'%i for i in range(2, 12)] + ['t%d'%i for i in range(3, 7)] + ["PC"]

class Regfile:
    def __init__(self):
        self.regs = [0]*33
    def __getitem__(self, key):
        return self.regs[key]
    def __setitem__(self, key, value):
        if key == 0:
            return 
        self.regs[key] = value & 0xFFFFFFFF

PC = 32

regfile = None
memory = None
def reset():
    global regfile, memory
    regfile = Regfile()
    # 8kb   at 0x80000000
    memory = b'\x00'*0x2000

from enum import Enum
#RV32I Base Instruction Set
class Ops(Enum):
    LUI = 0b0110111    # load upper immediate
    LOAD = 0b0000011
    STORE = 0b0100011

    AUIPC = 0b0010111  # add upper immediate to pc
    BRANCH = 0b1100011
    JAL = 0b1101111
    JALR = 0b1100111

    IMM = 0b0010011   
    OP = 0b0110011

    MISC = 0b0001111
    SYSTEM = 0b1110011
 
class Funct3(Enum):
    ADD = SUB = ADDI = 0b000
    SLLI = 0b001 
    SLT = SLTI = 0b010 
    SLTU = SLTUI = 0b011

    XOR = XORI = 0b100
    SRL = SRLI = SRA = SRAI = 0b101
    OR = ORI = 0b110
    AND = ANDI = 0b111

    BEQ = 0b000
    BNE = 0b001
    BLT = 0b100
    BGE = 0b101
    BLTU = 0b110
    BGEU = 0b111
    
    LB = SB = 0b000
    LH = SH = 0b001
    LW = SW = 0b010
    LBU = 0b100
    LHU = 0b101

    # Stupid instructions below this line
    ECALL = 0b000
    CSRRW = 0b001
    CSRRS = 0b010
    CSRRC = 0b011
    CSRRWI = 0b101
    CSRRSI = 0b110
    CSRRCI = 0b111

def ws(addr, dat):
    global memory
    #print(hex(addr), len(dat))
    addr -= 0x80000000
    assert  addr >= 0 and addr < len(memory)
    memory = memory[:addr] + dat + memory[addr+len(dat):]

def r32(addr):
    addr -=  0x80000000
    if addr < 0 or addr >= len(memory):
        raise Exception("read out of bounds: 0x%x" % addr)
    return struct.unpack("<I", memory[addr:addr+4])[0]

def dump():
    pp = []
    for i in range(33):
        if i % 8 == 0 and i != 0:
            pp += "\n"
        pp += " %3s: %08x" % (regnames[i], regfile[i])
    print(''.join(pp))

def sign_extend(x, l):
    if x >> (l-1) == 1:
        return -((1 << l) - x)
    else:
        return x

def arith(funct3, x, y, alt):
    if funct3 == Funct3.ADDI:
        if alt :
            return x - y
        else:
            return x + y
    elif funct3 == Funct3.SLLI:
        return x << (y&0x1f)
    elif funct3 == Funct3.SRLI:
        if alt:
            sb = x >> 31
            out = x >> (y&0x1f)
            out |= (0xFFFFFFFF * sb) << (32 - (y&0x1f))
            return out
        else:
            return x >> (y&0x1f)
    elif funct3 == Funct3.ORI:
        return x | y
    elif funct3 == Funct3.XORI:
        return x ^ y
    elif funct3 == Funct3.ANDI:
        return x & y
    elif funct3 == Funct3.SLT:
        return int(sign_extend(x, 32) < sign_extend(y, 32))
    elif funct3 == Funct3.SLTU:
        return int(x&0xFFFFFFFF < y&0xFFFFFFFF)
    else:
        dump()
        raise Exception("write funct3 %r" % (funct3))

def cond(funct3, vs1, vs2):
    if funct3 == Funct3.BEQ:
        return vs1 == vs2
    elif funct3 == Funct3.BNE:
         return vs1 != vs2
    elif funct3 == Funct3.BLT:
        return sign_extend(vs1, 32) < sign_extend(vs2, 32)
    elif funct3 == Funct3.BGE:
        return sign_extend(vs1, 32) >= sign_extend(vs2, 32)
    elif funct3 == Funct3.BLTU:
        return vs1 < vs2
    elif funct3 == Funct3.BGEU:
        return vs1 >= vs2
    else:
        dump()
        raise Exception("write %r funct3 %r" % (Ops.BRANCH, funct3))

def step():
    # *** Instruction Fetch ***
    ins = r32(regfile[PC]) 

    # *** Instruction Decode and Register Fetch ***
    def gibi(s, e):
        return ((ins >> e) & (1 << (s - e) + 1) - 1)

    opcode = Ops(gibi(6, 0))
    funct3 = Funct3(gibi(14, 12))
    funct7 = gibi(31, 25)
    imm_i = sign_extend(gibi(31, 20), 12)
    imm_u = sign_extend(gibi(31, 12) << 12, 32)
    imm_j = sign_extend(gibi(32, 31) << 20 | gibi(31, 21) << 1 | gibi(21, 20) << 11 | gibi(19, 12) << 12, 21)
    imm_b = sign_extend(gibi(32, 31) << 12 | gibi(31, 25) << 5 | gibi(11, 8) << 1 | gibi(8, 7) << 11, 13)
    imm_s = sign_extend(gibi(31, 25) << 5 | gibi(11, 7), 12)

    # register reads
    vs1 = regfile[gibi(19, 15)]
    vs2 = regfile[gibi(24, 20)]
    vpc = regfile[PC]

    # register write set up
    rd = gibi(11, 7) if opcode != Ops.BRANCH else 0 
    pend = None
    reg_writeback = False
    pend_is_new_pc = False
    do_load = False
    do_store = False
    
    #print("%x %8x %r" % (vpc, ins, opcode))

    # *** Execute ***
    if opcode == Ops.JAL:
        # J-type Instruction
        pend_is_new_pc = True
        pend = vpc + imm_j
    elif opcode == Ops.JALR:
        # I-type Instruction
        pend_is_new_pc = True
        pend = vs1 + imm_i
    elif opcode == Ops.BRANCH:
        # B-type Instruction
        if cond(funct3, vs1, vs2):
            pend_is_new_pc = True
            pend = vpc + imm_b
    elif opcode == Ops.AUIPC:
        #U-type Instruction
        reg_writeback = True
        pend = arith(Funct3.ADD, vpc, imm_u, False)
    elif opcode == Ops.LUI:
        #U-type Instruction
        pend = imm_u
        reg_writeback = True
    elif opcode == Ops.OP:
        # R-type Instruction
        pend = arith(funct3, vs1, vs2, funct7 == 0b0100000)
        reg_writeback = True
    elif opcode == Ops.IMM:
        # I-type Instruction
        pend = arith(funct3, vs1, imm_i, funct7 == 0b0100000 and funct3 == Funct3.SRAI)
        reg_writeback = True
    elif opcode == Ops.MISC:
        pass
    elif opcode == Ops.SYSTEM:
        # I-type instructions
        if funct3 == Funct3.CSRRW and imm_i == -1024:
            # hack for test exit
            return False
        elif funct3 == Funct3.ECALL:
            print("ecall", regfile[3])
            if regfile[3] > 1:
                raise Exception("FAILURE IN TEST, PLS CHECK")
    # Memory access step
    elif opcode == Ops.LOAD:
        # I-type Instruction
        pend = (vs1 + imm_i)
        do_load = True
        reg_writeback = True 
    elif opcode == Ops.STORE:
        # S-type Instruction
        pend = (vs1 + imm_s)
        do_store = True
    else:
        dump()
        raise Exception("wrtie op %r" % opcode)
    
    # *** Memory access ***
    if do_load:
        if funct3 == Funct3.LB:
            pend = sign_extend(r32(pend)&0xFF, 8)
        elif funct3 == Funct3.LH:
            pend = sign_extend(r32(pend)&0xFFFF, 16)
        elif funct3 == Funct3.LW:
            pend = r32(pend)
        elif funct3 == Funct3.LBU:
            pend = r32(pend)&0xFF
        elif funct3 == Funct3.LHU:
            pend = r32(pend)&0xFFFF
    elif do_store:
        if funct3 == Funct3.SB:
            ws(pend, struct.pack("B", vs2&0xFF))
        elif funct3 == Funct3.SH:
            ws(pend, struct.pack("H", vs2&0xFFFF))
        elif funct3 == Funct3.SW:
            ws(pend, struct.pack("I", vs2))

    # *** Register write back ***
    #dump()
    if pend_is_new_pc:
        regfile[rd] = vpc + 4
        regfile[PC] = pend
    else:
        if reg_writeback:
            regfile[rd] = pend
        regfile[PC] = vpc + 4
    return True

if __name__ == "__main__":
    if not os.path.isdir('test-cache'):
        os.mkdir('test-cache')
    for x in glob.glob("riscv-tests/isa/rv32ui-*"):
        if x.endswith('.dump'):
            continue
        try:
            with open(x, 'rb') as f:
                reset()
                print("test", x)
                print(f)
                e = ELFFile(f)
                for s in e.iter_segments():
                    ws(s.header.p_paddr, s.data())
                with open("test-cache/%s" % x.split("/")[-1], "wb") as g:
                    g.write(b'\n'.join([binascii.hexlify(memory[i:i+4][::-1]) for i in range(0,len(memory),4)]))
                regfile[PC] = 0x80000000
                #print(x, e, text)
                inscnt = 0
                while(step()):
                    inscnt += 1
                print("  ran %d instructions" % inscnt)
        except ELFError as elf_error:
            print(f"error processing {x}: {elf_error}")
            continue
        
