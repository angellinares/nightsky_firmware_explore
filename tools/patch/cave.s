@ NightSky per-step knob lanes - v16.
@ v10: chord moved to steps 3+6 (1+8 is the stock Expression setup), the ON
@ LED is purple while live recording is armed, clearing a lane or the first
@ record sets the lane's base.
@ v11-v15: the lanes persist. A preset save writes them to the preset slot
@ tail, a preset load reads them back, and a ring next to the stock
@ knob-state ring keeps the knob-mode lanes through a power-off.
@ v16: the debug parts (MIDI CC readout, counters, stack paint) build only
@ with DEBUG=1 (build_patch.py --debug).
@
@ Nine knob lanes (REVERB, DRY, DEPTH, INTERVAL, LOW CUT, LENGTH, SPEED,
@ SHIMMER, HIGH CUT), recorded per sequencer step, played back on every step.
@
@ Hooks:
@   T2   @ 0x080132A2  bl   dsp_send_param, after its push (record + playback)
@   POLL @ 0x08015C48  b.w  param_input_router entry (RAM init, chord detect)
@   LDHOOK @ 0x080121C4 b.w preset load    SVHOOK @ 0x080124A0 b.w preset save
@   JRHOOK @ 0x080152BC b.w stock knob-state ring write
@   DIAG @ 0x080144F8  b.w  CC handler entry (CC 120..127), DEBUG builds only
@
@ Gestures (sequencer running unless noted):
@   hold one step + turn a knob   -> store the knob value on that step
@   steps 3+6 chord, no knob      -> toggle live recording (on release)
@   live recording armed + knob   -> store the value on the playing step
@   hold steps 3+6 + turn a knob  -> clear that knob's lane (any time)
@   knob with no step held, not recording -> new base value for that lane
@
@ DSP ids: knob slot s = 0..7 -> id s+1; slot 8 -> id 10 (HIGH CUT).
@ id 9 (SIZE/PITCH) is the stock sequencer and stays untouched.
@ Each step the controller sends dsp_send_param(0x0B + step, 0, size).
@
@ RAM: 0x2000EC00, above .bss and the newlib-nano heap, below the stack.
@ The region 0x20000E70..0x20000F1F used by v3..v8 is a MORPH knob table.

    .syntax unified
    .cpu cortex-m4
    .thumb
    .text
    .ifndef DEBUG
    .equ DEBUG, 0
    .endif
    .global T2
    .global POLL
    .if DEBUG
    .global DIAG
    .endif
    .global LDHOOK
    .global SVHOOK
    .global JRHOOK

    .equ RAMB,       0x2000EC00
    .equ O_BASE,     0x90          @ 9 x u16 base values (lanes are at 0x00, 9 x 8 x u16)
    .equ O_GUARD,    0xA2          @ 0xA5 while we send our own messages
    .equ O_MAGIC,    0xA4          @ u16 0x5AA5 once initialised
    .equ O_HASREC,   0xA6          @ u16 bit per slot: lane holds a record
    .equ O_BASESET,  0xA8          @ u16 bit per slot: base value valid
    .equ O_ARMED,    0xAA          @ 0xA5 = live recording on
    .equ O_CPREV,    0xAB          @ chord was held at the last poll
    .equ O_CUSED,    0xAC          @ a knob cleared a lane during this chord
    .equ O_CUR,      0xAD          @ step of the last step-size message, 0xFF none
    .equ O_LEDIDX,   0xAE          @ LED painted while armed (default 0x21, CC 126 sets it)
    .equ O_LEDON,    0xAF          @ 1 = LED is purple, O_LEDSAV holds its old colour
    .equ O_LEDSAV,   0xB0          @ u32 colour of the LED before we painted it
    .equ O_LDCNT,    0xB4          @ u8 calls of FUN_080121c4 (preset load), rolls over
    .equ O_LDLAST,   0xB6          @ u16 preset number of the last load
    .equ O_RDP,      0xB8          @ u16 preset that CC 125 reads (CC 124 sets it)
    .equ O_SVCNT,    0xBA          @ u8 calls of FUN_080124a0 (preset save), rolls over
    .equ O_SVRES,    0xBB          @ u8 result of the last tail write (0xEE = skipped)
    .equ O_SVLAST,   0xBC          @ u16 preset number of the last save
    .equ O_LDRES,    0xC0          @ u8 result of the last lane restore (see LDHOOK)
    .equ O_RDA,      0xC4          @ u32 external flash address for CC 120 (CC 121-123 set it)
    .equ O_JRCNT,    0xC8          @ u8 lane-ring writes, rolls over
    .equ O_JRRES,    0xC9          @ u8 result of the last lane-ring write (0xEE skipped)
    .equ O_BOOTRES,  0xCA          @ u8 power-up restore: 1 ok, 2 no record, 3 CRC bad,
                                   @ 4 counter differs, 7 bad page, 8 not tried
    .equ RAM_LEN,    0xCC
    .equ LN_RING,    0x130000      @ lane ring: page i pairs with stock page i
    .equ XF_PROG,    0x08012719    @ FUN_08012718(addr, len, buf): page program, no erase
    .equ XF_ERASE,   0x08012795    @ FUN_08012794(addr, cmd): cmd 0x20 = 4 KB sector erase
    .equ MARKDIRTY,  0x08015361    @ FUN_08015360: stock "knob state changed"
    .equ NORESTORE,  0x0BAD        @ O_MAGIC value after CC clear: init without restore
    .equ JR_IDX,     0x20008882    @ u16 stock knob-state ring: current page (0..0x3FF)
    .equ JR_CNT,     0x20008884    @ u32 stock knob-state ring: write counter
    .equ XF_WRITE,   0x0801281D    @ FUN_0801281c(addr, len, buf): external flash write
    .equ REC_OFF,    0x700         @ tail record inside the 0x800 slot
    .equ REC_LEN,    0xC0
    .equ REC_DATA,   0xAA          @ RAM block 0x00..0xA9 goes into the record
    .equ REC_MAGIC,  0x4C4E
    .equ REC_VER,    1
    .equ NPRESET,    0x12D
    .equ XF_READ,    0x08012629    @ FUN_08012628(addr, len, buf): external flash read
    .equ SLOT0,      0x00040000    @ preset p at SLOT0 + p * 0x800, 0x4FC bytes used
    .equ TAIL,       0x4FC
    .equ LEDTAB,     0x200009D4    @ 34 LEDs x 0x18 bytes, colour 0x00RRGGBB at +4
    .equ LEDSET,     0x080137F9    @ FUN_080137f8(led, colour)
    .equ LED_DEF,    0x21          @ ON footswitch LED (measured; 0x20 is not visible)
    .equ PURPLE,     0x008000FF
    .equ CH_A,       2             @ chord steps 3 and 6 (index 2, 5)
    .equ CH_B,       5
    .equ PAINT_LO,   0x2000ED00    @ stack paint starts here (diagnostic)
    .equ HELD,       0x20000F8A    @ held flags, step i at +i, 0 = held
    .equ RUNFLAG,    0x200088DD    @ 1 = sequencer running
    .equ TOGGLE,     0x2000888E    @ stock SIZE path clears it after an edit
    .equ EDITFLG,    0x200088CE    @ FUN_080193d8 reads it; nonzero = no step toggle
    .equ MAGICV,     0x5AA5

@ ================= T2: record + playback =================
@ Saved: id@sp+0, type@sp+4, value@sp+8.
    .align 2
    .thumb_func
T2:
    push.w {r0-r8, lr}
    ldr  r8, =RAMB
    ldrh r5, [r8, #O_MAGIC]
    movw r4, #MAGICV
    cmp  r5, r4
    bne  T2_skip                   @ RAM not initialised yet
    ldrb r5, [r8, #O_GUARD]
    cmp  r5, #0xA5
    beq  T2_skip                   @ our own nested send
    ldr  r1, [sp, #4]              @ type
    cmp  r1, #0
    bne  T2_skip                   @ only live parameter writes
    ldr  r0, [sp, #0]              @ id
    subs r2, r0, #0x0B
    cmp  r2, #8
    bhs  T2_knob
@ ---- step-size message: remember the step, play every lane with records ----
    strb r2, [r8, #O_CUR]
    ldrh r6, [r8, #O_HASREC]
    cmp  r6, #0
    beq  T2_skip
    mov  r7, r2                    @ r7 = step
    movs r5, #0                    @ r5 = slot
T2_pl:
    movs r3, #1
    lsls r3, r3, r5
    tst  r6, r3
    beq  T2_pnext
    lsls r4, r5, #4
    add  r4, r4, r7, lsl #1
    ldrh r1, [r8, r4]              @ lane[slot][step]
    movw r4, #0xFFFF
    cmp  r1, r4
    bne  T2_psend
    ldrh r4, [r8, #O_BASESET]      @ unrecorded step -> base value
    tst  r4, r3
    beq  T2_pnext
    add  r4, r8, #O_BASE
    ldrh r1, [r4, r5, lsl #1]
T2_psend:
    adds r0, r5, #1                @ id = slot + 1
    cmp  r5, #8
    it   eq
    moveq r0, #10                  @ slot 8 = HIGH CUT
    mov  r2, r1
    movs r1, #0
    movs r4, #0xA5
    strb r4, [r8, #O_GUARD]
    ldr  r4, =0x080132A1
    blx  r4                        @ dsp_send_param(id, 0, value)
    movs r4, #0
    strb r4, [r8, #O_GUARD]
T2_pnext:
    adds r5, r5, #1
    cmp  r5, #9
    blt  T2_pl
    b    T2_skip
@ ---- knob message ----
T2_knob:
    subs r5, r0, #1                @ slot = id - 1 for ids 1..8
    cmp  r5, #8
    blo  T2_kslot
    cmp  r0, #10
    bne  T2_skip                   @ not one of our knobs
    movs r5, #8
T2_kslot:
    ldr  r0, =HELD
    movs r1, #0
    movs r4, #0                    @ held count
    movs r6, #0xFF                 @ held step
T2_ks:
    ldrb r2, [r0, r1]
    cmp  r2, #0
    bne  T2_kn
    mov  r6, r1
    adds r4, r4, #1
T2_kn:
    adds r1, r1, #1
    cmp  r1, #8
    blt  T2_ks
    cmp  r4, #2
    bne  T2_one
    ldrb r2, [r0, #CH_A]           @ chord = exactly steps 3 and 6
    cmp  r2, #0
    bne  T2_skip
    ldrb r2, [r0, #CH_B]
    cmp  r2, #0
    bne  T2_skip
    lsls r1, r5, #4                @ clear lane[slot]
    add  r1, r8, r1
    movs r2, #16
    movs r3, #0xFF
T2_clr:
    subs r2, r2, #1
    strb r3, [r1, r2]
    bne  T2_clr
    ldrh r2, [r8, #O_HASREC]
    movs r3, #1
    lsls r3, r3, r5
    bic  r2, r2, r3
    strh r2, [r8, #O_HASREC]
    movs r2, #1
    strb r2, [r8, #O_CUSED]
    ldr  r12, =MARKDIRTY
    blx  r12                       @ the stock timer saves the lane ring too
    b    T2_base                   @ the knob position becomes the lane's base
T2_one:
    cmp  r4, #1
    bne  T2_none
    ldr  r2, =RUNFLAG
    ldrb r2, [r2]
    cmp  r2, #1
    bne  T2_skip
    movs r2, #0xA5
    strb r2, [r8, #O_GUARD]
    mov  r0, r6
    ldr  r3, =0x08019CA1
    blx  r3                        @ FUN_08019ca0(step): keep the held step lit
    ldr  r0, =TOGGLE
    movs r1, #0
    strb r1, [r0]
    movs r2, #0
    strb r2, [r8, #O_GUARD]
    mov  r1, r6
    b    T2_store
T2_none:
    cmp  r4, #0
    bne  T2_skip
    ldrb r2, [r8, #O_ARMED]
    cmp  r2, #0xA5
    bne  T2_base
    ldr  r2, =RUNFLAG
    ldrb r2, [r2]
    cmp  r2, #1
    bne  T2_base
    ldrb r1, [r8, #O_CUR]
    cmp  r1, #8
    bhs  T2_base
    b    T2_store                  @ live recording into the playing step
T2_base:
    add  r2, r8, #O_BASE
    ldr  r3, [sp, #8]
    strh r3, [r2, r5, lsl #1]
    ldrh r2, [r8, #O_BASESET]
    movs r3, #1
    lsls r3, r3, r5
    orrs r2, r3
    strh r2, [r8, #O_BASESET]
    b    T2_skip
T2_store:                          @ r1 = step, r5 = slot
    lsls r2, r5, #4
    add  r2, r2, r1, lsl #1
    ldr  r3, [sp, #8]
    strh r3, [r8, r2]
    ldrh r2, [r8, #O_HASREC]
    movs r3, #1
    lsls r3, r3, r5
    orrs r2, r3
    strh r2, [r8, #O_HASREC]
    ldr  r12, =MARKDIRTY
    blx  r12                       @ clobbers r2, r3 only
    ldrh r2, [r8, #O_BASESET]      @ no base yet: the first record is the base
    movs r3, #1
    lsls r3, r3, r5
    tst  r2, r3
    beq  T2_base
T2_skip:
    pop.w {r0-r8, lr}
    ldr  r3, =0x200076A6           @ displaced: ldr r3,[0x080132e4]
    ldrb r3, [r3]                  @ displaced: ldrb r3,[r3]
    bx   lr                        @ back to 0x080132A6
    .pool

@ ================= POLL: param_input_router entry =================
@ Entered via b.w from 0x08015C48. No arguments. lr = caller.
    .align 2
    .thumb_func
POLL:
    push {r4, r5, r6, lr}
    ldr  r4, =RAMB
    ldrh r0, [r4, #O_MAGIC]
    movw r1, #MAGICV
    cmp  r0, r1
    beq  P_ready
    mov  r5, r0                    @ r5 = old magic (NORESTORE after CC clear)
    movs r0, #0                    @ first run: lanes = 0xFFFF
    movs r1, #0xFF
P_i1:
    strb r1, [r4, r0]
    adds r0, r0, #1
    cmp  r0, #O_BASE
    blt  P_i1
    movs r1, #0                    @ base values and flags = 0
P_i2:
    strb r1, [r4, r0]
    adds r0, r0, #1
    cmp  r0, #RAM_LEN
    blt  P_i2
    movs r1, #0xFF
    strb r1, [r4, #O_CUR]
    movs r1, #LED_DEF
    strb r1, [r4, #O_LEDIDX]
    .if DEBUG
    ldr  r0, =PAINT_LO             @ paint the unused stack area
    mov  r1, sp
    sub  r1, r1, #256
    movs r2, #0xA5
P_pt:
    cmp  r0, r1
    bhs  P_pd
    strb r2, [r0], #1
    b    P_pt
P_pd:
    .endif
    movw r1, #MAGICV
    strh r1, [r4, #O_MAGIC]
    .if DEBUG
    movs r1, #8
    strb r1, [r4, #O_BOOTRES]
    movw r1, #NORESTORE            @ CC clear: init without the restore
    cmp  r5, r1
    beq  P_ready
    .endif
    bl   LNRESTORE                 @ power-up: lanes from the lane ring
P_ready:
    ldr  r0, =HELD                 @ chord = exactly steps 3 and 6 held
    movs r1, #0
    movs r2, #0
P_s:
    ldrb r3, [r0, r1]
    cmp  r3, #0
    bne  P_n
    adds r2, r2, #1
P_n:
    adds r1, r1, #1
    cmp  r1, #8
    blt  P_s
    movs r6, #0
    cmp  r2, #2
    bne  P_c
    ldrb r3, [r0, #CH_A]
    cmp  r3, #0
    bne  P_c
    ldrb r3, [r0, #CH_B]
    cmp  r3, #0
    bne  P_c
    movs r6, #1
P_c:
    ldrb r3, [r4, #O_CPREV]
    cmp  r6, #0
    beq  P_rel
    cmp  r3, #0                    @ chord held
    bne  P_hold
    movs r3, #1
    strb r3, [r4, #O_CPREV]
    movs r3, #0
    strb r3, [r4, #O_CUSED]
P_hold:
    ldr  r0, =TOGGLE
    movs r3, #0
    strb r3, [r0]
    ldr  r0, =EDITFLG              @ stock "edit happened": the router skips the
    ldrb r3, [r0]                  @ step toggle on release while it is set, and
    cmp  r3, #0                    @ clears it when every button is up. Value 2,
    bne  P_out                     @ not 1: 1 also restores saved step LEDs.
    movs r3, #2
    strb r3, [r0]
    b    P_out
P_rel:
    cmp  r3, #0
    beq  P_out
    movs r3, #0                    @ chord just released
    strb r3, [r4, #O_CPREV]
    ldrb r3, [r4, #O_CUSED]
    cmp  r3, #0
    bne  P_out                     @ the chord cleared a lane: no toggle
    ldrb r3, [r4, #O_ARMED]
    cmp  r3, #0xA5
    ite  eq
    moveq r3, #0
    movne r3, #0xA5
    strb r3, [r4, #O_ARMED]
P_out:                             @ ON LED purple while armed
    ldrb r0, [r4, #O_ARMED]
    cmp  r0, #0xA5
    beq  P_lon
    bl   LED_OFF
    b    P_end
P_lon:
    ldrb r0, [r4, #O_LEDIDX]
    cmp  r0, #0x22
    bhs  P_end
    ldr  r1, =LEDTAB
    movs r2, #0x18
    mla  r1, r0, r2, r1
    ldr  r1, [r1, #4]              @ current colour
    ldr  r2, =PURPLE
    cmp  r1, r2
    beq  P_end                     @ already purple
    str  r1, [r4, #O_LEDSAV]       @ the stock colour, also after a stock repaint
    mov  r1, r2
    movs r2, #1
    strb r2, [r4, #O_LEDON]
    ldr  r3, =LEDSET
    blx  r3
P_end:
    pop  {r4, r5, r6, lr}
    push.w {r4-r11, lr}            @ displaced
    ldr  r12, =0x08015C4D
    bx   r12                       @ continue at 0x08015C4C
    .pool

@ ================= LDHOOK: FUN_080121c4 entry (preset load) =================
@ Entered via b.w from 0x080121C4. r0 = preset. Counts the call and keeps
@ the preset number. p = 0x7F (back to knob mode) or p >= 0x12D: stock only,
@ the lanes stay. Otherwise the stock load runs first, then the hook reads
@ the tail record. Magic, version, CRC and preset checksum all match: copy
@ lanes, bases, HASREC and BASESET into RAM. Else: clear them.
@ O_LDRES: 1 restored, 2 no record, 3 CRC bad, 4 checksum differs,
@ 5 stock only, 6 lane RAM not initialised.
    .align 2
    .thumb_func
LDHOOK:
    .if DEBUG
    ldr  r1, =RAMB
    ldrb r2, [r1, #O_LDCNT]
    adds r2, r2, #1
    strb r2, [r1, #O_LDCNT]
    strh r0, [r1, #O_LDLAST]
    movs r2, #5
    strb r2, [r1, #O_LDRES]
    .endif
    cmp  r0, #0x7F
    beq  STOCK_LOAD                @ tail call, returns to the caller
    movw r2, #NPRESET
    cmp  r0, r2
    bhs  STOCK_LOAD
    push {r4, r5, r6, lr}
    sub  sp, sp, #REC_LEN + 8      @ record at sp+0, slot checksum at sp+0xC0
    mov  r4, r0
    bl   STOCK_LOAD
    ldr  r5, =RAMB
    .if DEBUG
    movs r0, #6
    strb r0, [r5, #O_LDRES]
    .endif
    ldrh r0, [r5, #O_MAGIC]
    movw r1, #MAGICV
    cmp  r0, r1
    bne  L_out
    ldr  r6, =SLOT0
    add  r6, r6, r4, lsl #11       @ r6 = slot address
    add  r0, r6, #REC_OFF
    movs r1, #REC_LEN
    mov  r2, sp
    ldr  r3, =XF_READ
    blx  r3                        @ the record
    add  r0, r6, #0x4F8
    movs r1, #4
    add  r2, sp, #REC_LEN
    ldr  r3, =XF_READ
    blx  r3                        @ the checksum of the preset in the slot
    movs r6, #2
    ldrh r0, [sp, #0]
    movw r1, #REC_MAGIC
    cmp  r0, r1
    bne  L_clr
    ldrh r0, [sp, #2]
    cmp  r0, #REC_VER
    bne  L_clr
    movs r6, #3
    mov  r0, sp
    movs r1, #0xB2
    bl   CRC16
    ldrh r1, [sp, #0xB2]
    cmp  r0, r1
    bne  L_clr
    movs r6, #4
    ldr  r0, [sp, #4]
    ldr  r1, [sp, #REC_LEN]
    cmp  r0, r1
    bne  L_clr
    movs r0, #0                    @ lanes 0x00..0x8F and bases 0x90..0xA1
    add  r2, sp, #8
L_cp:
    ldrb r1, [r2, r0]
    strb r1, [r5, r0]
    adds r0, r0, #1
    cmp  r0, #O_GUARD
    blt  L_cp
    ldrh r0, [r2, #O_HASREC]       @ halfwords: 0xA6 is not word aligned
    strh r0, [r5, #O_HASREC]
    ldrh r0, [r2, #O_BASESET]
    strh r0, [r5, #O_BASESET]
    movs r6, #1
    b    L_res
L_clr:
    movs r0, #0                    @ lanes = 0xFFFF, bases 0, no flags
    movs r1, #0xFF
L_c1:
    strb r1, [r5, r0]
    adds r0, r0, #1
    cmp  r0, #O_BASE
    blt  L_c1
    movs r1, #0
L_c2:
    strb r1, [r5, r0]
    adds r0, r0, #1
    cmp  r0, #O_GUARD
    blt  L_c2
    strh r1, [r5, #O_HASREC]
    strh r1, [r5, #O_BASESET]
L_res:
    .if DEBUG
    strb r6, [r5, #O_LDRES]
    .endif
L_out:
    add  sp, sp, #REC_LEN + 8
    pop  {r4, r5, r6, pc}
    .pool

@ ================= JRHOOK: FUN_080152bc entry (stock knob-state ring write) ======
@ Entered via b.w from 0x080152BC. r0 = previous page. The stock write runs
@ first and leaves the new page in JR_IDX and the counter in JR_CNT. Then
@ the hook writes the lane record (same layout as the slot tail record, with
@ the ring counter at +0x04) to LN_RING + page * 0x100. A sector is erased
@ only when the page is not blank, the same rule as the stock ring.
    .align 2
    .thumb_func
JRHOOK:
    push {r4, r5, r6, lr}
    sub  sp, sp, #REC_LEN + 8      @ record at sp+0, blank check at sp+0xC0
    bl   STOCK_JR                  @ r0 = previous page
    ldr  r5, =RAMB
    .if DEBUG
    ldrb r0, [r5, #O_JRCNT]
    adds r0, r0, #1
    strb r0, [r5, #O_JRCNT]
    movs r0, #0xEE
    strb r0, [r5, #O_JRRES]
    .endif
    ldrh r0, [r5, #O_MAGIC]
    movw r1, #MAGICV
    cmp  r0, r1
    bne  J_out                     @ lane RAM not initialised
    ldr  r1, =JR_IDX
    ldrh r4, [r1]
    cmp  r4, #0x400
    bhs  J_out
    ldr  r6, =LN_RING
    add  r6, r6, r4, lsl #8        @ r6 = lane page
    mov  r0, r6
    movs r1, #4
    add  r2, sp, #REC_LEN
    ldr  r3, =XF_READ
    blx  r3
    ldr  r0, [sp, #REC_LEN]
    adds r0, r0, #1
    beq  J_blank                   @ 0xFFFFFFFF: page is blank
    mov  r0, r6
    movs r1, #0x20
    ldr  r3, =XF_ERASE
    blx  r3                        @ erase the 4 KB sector of this page
J_blank:
    movw r0, #REC_MAGIC
    strh r0, [sp, #0]
    movs r0, #REC_VER
    strh r0, [sp, #2]
    ldr  r1, =JR_CNT
    ldr  r0, [r1]
    str  r0, [sp, #4]              @ tag: the stock ring counter
    movs r0, #0
J_cp:
    ldrb r1, [r5, r0]
    add  r2, sp, #8
    strb r1, [r2, r0]
    adds r0, r0, #1
    cmp  r0, #REC_DATA
    blt  J_cp
    mov  r0, sp
    movs r1, #0xB2
    bl   CRC16
    strh r0, [sp, #0xB2]
    movs r0, #0xB4
    movs r1, #0xFF
J_ff:
    strb r1, [sp, r0]
    adds r0, r0, #1
    cmp  r0, #REC_LEN
    blt  J_ff
    mov  r0, r6
    movs r1, #REC_LEN
    mov  r2, sp
    ldr  r3, =XF_PROG
    blx  r3
    .if DEBUG
    strb r0, [r5, #O_JRRES]
    .endif
J_out:
    add  sp, sp, #REC_LEN + 8
    pop  {r4, r5, r6, pc}
    .pool

@ STOCK_JR: the stock FUN_080152bc body. r0 = previous page.
    .align 2
    .thumb_func
STOCK_JR:
    push {r0, r1, r4, r5, r6, lr}  @ displaced
    adds r0, r0, #1                @ displaced
    ldr  r12, =0x080152C1
    bx   r12                       @ continue at 0x080152C0
    .pool

@ LNRESTORE: r4 = RAMB, lane RAM just initialised (power-up). Read the lane
@ page that pairs with the stock page in JR_IDX. Copy it only if magic,
@ version, CRC and the ring counter all match. Result in O_BOOTRES.
@ Clobbers r0-r3, r12.
    .align 2
    .thumb_func
LNRESTORE:
    push {r4, r5, r6, lr}
    sub  sp, sp, #REC_LEN
    mov  r5, r4
    movs r6, #7
    ldr  r1, =JR_IDX
    ldrh r0, [r1]
    cmp  r0, #0x400
    bhs  R_res
    ldr  r1, =LN_RING
    add  r0, r1, r0, lsl #8
    movs r1, #REC_LEN
    mov  r2, sp
    ldr  r3, =XF_READ
    blx  r3
    movs r6, #2
    ldrh r0, [sp, #0]
    movw r1, #REC_MAGIC
    cmp  r0, r1
    bne  R_res
    ldrh r0, [sp, #2]
    cmp  r0, #REC_VER
    bne  R_res
    movs r6, #3
    mov  r0, sp
    movs r1, #0xB2
    bl   CRC16
    ldrh r1, [sp, #0xB2]
    cmp  r0, r1
    bne  R_res
    movs r6, #4
    ldr  r0, [sp, #4]
    ldr  r1, =JR_CNT
    ldr  r1, [r1]
    cmp  r0, r1
    bne  R_res
    movs r0, #0                    @ lanes 0x00..0x8F and bases 0x90..0xA1
    add  r2, sp, #8
R_cp:
    ldrb r1, [r2, r0]
    strb r1, [r5, r0]
    adds r0, r0, #1
    cmp  r0, #O_GUARD
    blt  R_cp
    ldrh r0, [r2, #O_HASREC]
    strh r0, [r5, #O_HASREC]
    ldrh r0, [r2, #O_BASESET]
    strh r0, [r5, #O_BASESET]
    movs r6, #1
R_res:
    .if DEBUG
    strb r6, [r5, #O_BOOTRES]
    .endif
    add  sp, sp, #REC_LEN
    pop  {r4, r5, r6, pc}
    .pool

@ STOCK_LOAD: the stock FUN_080121c4 body. r0 = preset.
    .align 2
    .thumb_func
STOCK_LOAD:
    push {r3, r4, r5, lr}          @ displaced
    mov  r4, r0                    @ displaced
    ldr  r3, =0x080121C9
    bx   r3                        @ continue at 0x080121C8
    .pool

@ ================= SVHOOK: FUN_080124a0 entry (preset save) =================
@ Entered via b.w from 0x080124A0. r0 = preset. The stock save runs first.
@ Then the hook writes the tail record at slot + 0x700:
@   +0x00 u16 magic 0x4C4E, +0x02 u16 version, +0x04 u32 preset checksum
@   (read back from slot + 0x4F8), +0x08 RAM block 0x00..0xA9,
@   +0xB2 u16 CRC-16/CCITT of +0x00..+0xB1, +0xB4..+0xBF 0xFF.
    .align 2
    .thumb_func
SVHOOK:
    push {r4, r5, r6, lr}
    sub  sp, sp, #REC_LEN
    mov  r4, r0                    @ r4 = preset
    bl   STOCK_SAVE                @ r0 = preset
    ldr  r5, =RAMB
    .if DEBUG
    ldrb r0, [r5, #O_SVCNT]
    adds r0, r0, #1
    strb r0, [r5, #O_SVCNT]
    strh r4, [r5, #O_SVLAST]
    movs r0, #0xEE
    strb r0, [r5, #O_SVRES]
    .endif
    movw r0, #NPRESET
    cmp  r4, r0
    bhs  S_out                     @ stock did not write either
    ldrh r0, [r5, #O_MAGIC]
    movw r1, #MAGICV
    cmp  r0, r1
    bne  S_out                     @ lane RAM not initialised
    ldr  r6, =SLOT0
    add  r6, r6, r4, lsl #11       @ r6 = slot address
    add  r0, r6, #0x4F8
    movs r1, #4
    add  r2, sp, #4
    ldr  r3, =XF_READ
    blx  r3                        @ checksum the stock save just wrote
    movw r0, #REC_MAGIC
    strh r0, [sp, #0]
    movs r0, #REC_VER
    strh r0, [sp, #2]
    movs r0, #0
S_cp:
    ldrb r1, [r5, r0]
    add  r2, sp, #8
    strb r1, [r2, r0]
    adds r0, r0, #1
    cmp  r0, #REC_DATA
    blt  S_cp
    mov  r0, sp
    movs r1, #0xB2
    bl   CRC16
    strh r0, [sp, #0xB2]
    movs r0, #0xB4
    movs r1, #0xFF
S_ff:
    strb r1, [sp, r0]
    adds r0, r0, #1
    cmp  r0, #REC_LEN
    blt  S_ff
    add  r0, r6, #REC_OFF
    movs r1, #REC_LEN
    mov  r2, sp
    ldr  r3, =XF_WRITE
    blx  r3                        @ FUN_0801281c(slot + 0x700, 0xC0, rec)
    .if DEBUG
    strb r0, [r5, #O_SVRES]
    .endif
S_out:
    add  sp, sp, #REC_LEN
    pop  {r4, r5, r6, pc}
    .pool

@ STOCK_SAVE: call the stock FUN_080124a0 body. r0 = preset.
@ It returns to our lr through its own pop / tail call.
    .align 2
    .thumb_func
STOCK_SAVE:
    push {r3, r4, r5, lr}          @ displaced
    mov  r4, r0                    @ displaced
    ldr  r3, =0x080124A5
    bx   r3                        @ continue at 0x080124A4
    .pool

@ CRC16: CRC-16/CCITT (poly 0x1021, init 0xFFFF). r0 = buf, r1 = len.
@ Returns r0 = CRC. Clobbers r1-r3, r12.
    .align 2
    .thumb_func
CRC16:
    push {r4, lr}
    movw r2, #0xFFFF
    movw r4, #0x1021
C_b:
    ldrb r3, [r0], #1
    eor  r2, r2, r3, lsl #8
    mov  r12, #8
C_i:
    lsls r2, r2, #1
    tst  r2, #0x10000
    it   ne
    eorne r2, r2, r4
    uxth r2, r2
    subs r12, r12, #1
    bne  C_i
    subs r1, r1, #1
    bne  C_b
    mov  r0, r2
    pop  {r4, pc}

@ LED_OFF: r4 = RAMB. If we painted an LED, give it back its old colour.
@ Clobbers r0-r3, r12.
    .align 2
    .thumb_func
LED_OFF:
    ldrb r0, [r4, #O_LEDON]
    cmp  r0, #1
    bne  L_ret
    push {r4, lr}
    movs r0, #0
    strb r0, [r4, #O_LEDON]
    ldrb r0, [r4, #O_LEDIDX]
    ldr  r1, [r4, #O_LEDSAV]
    ldr  r3, =LEDSET
    blx  r3
    pop  {r4, lr}
L_ret:
    bx   lr
    .pool

    .if DEBUG
@ ================= DIAG: CC handler entry (DEBUG builds only) =================
@ Entered via b.w from 0x080144F8. r0 = CC number, r1 = value.
@ CC 127 = 0x45: status. 0x46: clear everything. 0x50..0x58: dump lane 0..8.
@ CC 126 = n (0..33): LED to paint purple while armed.
    .align 2
    .thumb_func
DIAG:
    cmp  r0, #0x78
    beq  D_any
    cmp  r0, #0x79
    beq  D_a2
    cmp  r0, #0x7A
    beq  D_a1
    cmp  r0, #0x7B
    beq  D_a0
    cmp  r0, #0x7C
    beq  D_rdp
    cmp  r0, #0x7D
    beq  D_tail
    cmp  r0, #0x7E
    beq  D_led
    cmp  r0, #0x7F
    bne  D_pass
    cmp  r1, #0x45
    beq  D_stat
    cmp  r1, #0x46
    beq  D_reset
    subs r2, r1, #0x50
    cmp  r2, #9
    blo  D_lane
D_pass:
    cmp  r0, #0x51                 @ displaced (flags used at 0x08014500)
    push {r4, r5, r6, lr}          @ displaced
    ldr  r12, =0x080144FD
    bx   r12
D_a2:                              @ CC 121 = address bits 20..14
    ldr  r2, =RAMB
    ldr  r3, [r2, #O_RDA]
    bic  r3, r3, #0x1FC000
    orr  r3, r3, r1, lsl #14
    str  r3, [r2, #O_RDA]
    bx   lr
D_a1:                              @ CC 122 = address bits 13..7
    ldr  r2, =RAMB
    ldr  r3, [r2, #O_RDA]
    bic  r3, r3, #0x3F80
    orr  r3, r3, r1, lsl #7
    str  r3, [r2, #O_RDA]
    bx   lr
D_a0:                              @ CC 123 = address bits 6..0
    ldr  r2, =RAMB
    ldr  r3, [r2, #O_RDA]
    bic  r3, r3, #0x7F
    orr  r3, r3, r1
    str  r3, [r2, #O_RDA]
    bx   lr
D_any:                             @ CC 120 = c: read 32 bytes at O_RDA + c * 32
    push {r4, r5, r6, lr}          @ (read only), reply cmd 0x64
    sub  sp, sp, #104
    mov  r5, r1
    ldr  r4, =RAMB
    ldr  r0, [r4, #O_RDA]
    add  r0, r0, r5, lsl #5
    movs r1, #32
    add  r2, sp, #72
    ldr  r3, =XF_READ
    blx  r3
    movs r0, #0x64
    strb r0, [sp, #0]
    strb r5, [sp, #1]
    add  r1, sp, #72
    add  r2, sp, #2
    movs r3, #32
D_an:
    ldrb r0, [r1], #1
    lsrs r6, r0, #4
    strb r6, [r2], #1
    and  r0, r0, #0x0F
    strb r0, [r2], #1
    subs r3, r3, #1
    bne  D_an
    mov  r0, sp
    movs r1, #66                   @ cmd + chunk + 64 nibbles
    ldr  r3, =0x0801408D
    blx  r3
    add  sp, sp, #104
    pop  {r4, r5, r6, pc}
D_rdp:                             @ CC 124 = p: preset for CC 125 (0..127)
    ldr  r2, =RAMB
    strh r1, [r2, #O_RDP]
    bx   lr
D_tail:                            @ CC 125 = c (0..24): read 32 bytes of the
    cmp  r1, #25                   @ slot tail at 0x4FC + c * 32 (read only)
    bhs  D_ret
    push {r4, r5, r6, lr}
    sub  sp, sp, #104              @ 32 raw bytes at sp+72, reply at sp+0
    mov  r5, r1                    @ r5 = chunk
    ldr  r4, =RAMB
    ldrh r6, [r4, #O_RDP]          @ r6 = preset
    ldr  r0, =SLOT0 + TAIL
    add  r0, r0, r6, lsl #11       @ + p * 0x800
    add  r0, r0, r5, lsl #5        @ + c * 32
    movs r1, #32
    add  r2, sp, #72
    ldr  r3, =XF_READ
    blx  r3                        @ FUN_08012628(addr, 32, buf)
    movs r0, #0x60
    strb r0, [sp, #0]
    and  r0, r6, #0x7F
    strb r0, [sp, #1]
    strb r5, [sp, #2]
    add  r1, sp, #72               @ src
    add  r2, sp, #3                @ dst: two nibbles per byte, high first
    movs r3, #32
D_tn:
    ldrb r0, [r1], #1
    lsrs r6, r0, #4
    strb r6, [r2], #1
    and  r0, r0, #0x0F
    strb r0, [r2], #1
    subs r3, r3, #1
    bne  D_tn
    mov  r0, sp
    movs r1, #67                   @ cmd + preset + chunk + 64 nibbles
    ldr  r3, =0x0801408D
    blx  r3
    add  sp, sp, #104
    pop  {r4, r5, r6, pc}
D_led:                             @ CC 126 = n: paint LED n while armed
    cmp  r1, #0x22
    bhs  D_ret
    push {r4, r5, r6, lr}
    mov  r5, r1
    ldr  r4, =RAMB
    ldrh r0, [r4, #O_MAGIC]
    movw r1, #MAGICV
    cmp  r0, r1
    bne  D_lx
    bl   LED_OFF                   @ give the old LED its colour back
    strb r5, [r4, #O_LEDIDX]       @ the next poll paints the new one
D_lx:
    pop  {r4, r5, r6, pc}
D_reset:
    push {r4, lr}
    ldr  r4, =RAMB
    ldrh r0, [r4, #O_MAGIC]
    movw r1, #MAGICV
    cmp  r0, r1
    bne  D_rx
    bl   LED_OFF
D_rx:
    movw r3, #NORESTORE            @ drop the magic: the next poll re-initialises,
    strh r3, [r4, #O_MAGIC]        @ without the power-up restore
    pop  {r4, pc}
D_ret:
    bx   lr
D_stat:
    push {r4, r5, r6, lr}
    sub  sp, sp, #32
    ldr  r4, =RAMB
    movs r0, #0x45
    strb r0, [sp, #0]
    ldrb r0, [r4, #O_ARMED]
    cmp  r0, #0xA5
    ite  eq
    moveq r0, #1
    movne r0, #0
    strb r0, [sp, #1]
    ldrb r0, [r4, #O_CPREV]
    and  r0, r0, #0x7F
    strb r0, [sp, #2]
    ldrb r0, [r4, #O_CUSED]
    and  r0, r0, #0x7F
    strb r0, [sp, #3]
    ldrb r0, [r4, #O_CUR]
    and  r0, r0, #0x7F
    strb r0, [sp, #4]
    ldrh r0, [r4, #O_HASREC]
    and  r1, r0, #0x7F
    strb r1, [sp, #5]
    lsrs r1, r0, #7
    and  r1, r1, #0x7F
    strb r1, [sp, #6]
    ldrh r0, [r4, #O_BASESET]
    and  r1, r0, #0x7F
    strb r1, [sp, #7]
    lsrs r1, r0, #7
    and  r1, r1, #0x7F
    strb r1, [sp, #8]
    ldrb r0, [r4, #O_GUARD]
    and  r0, r0, #0x7F
    strb r0, [sp, #9]
    ldrh r0, [r4, #O_MAGIC]
    movw r1, #MAGICV
    cmp  r0, r1
    ite  eq
    moveq r0, #1
    movne r0, #0
    strb r0, [sp, #10]
    ldr  r0, =PAINT_LO             @ stack margin: untouched paint bytes
    mov  r1, sp
D_sc:
    cmp  r0, r1
    bhs  D_sd
    ldrb r2, [r0]
    cmp  r2, #0xA5
    bne  D_sd
    adds r0, r0, #1
    b    D_sc
D_sd:
    ldr  r1, =PAINT_LO
    subs r0, r0, r1
    and  r1, r0, #0x7F
    strb r1, [sp, #11]
    lsrs r1, r0, #7
    and  r1, r1, #0x7F
    strb r1, [sp, #12]
    ldrb r0, [r4, #O_LEDIDX]
    and  r0, r0, #0x7F
    strb r0, [sp, #13]
    ldrb r0, [r4, #O_LEDON]
    and  r0, r0, #0x7F
    strb r0, [sp, #14]
    ldrb r0, [r4, #O_LDCNT]
    and  r0, r0, #0x7F
    strb r0, [sp, #15]
    ldrh r0, [r4, #O_LDLAST]
    lsrs r1, r0, #7
    and  r1, r1, #0x7F
    strb r1, [sp, #16]
    and  r0, r0, #0x7F
    strb r0, [sp, #17]
    ldrb r0, [r4, #O_SVCNT]
    and  r0, r0, #0x7F
    strb r0, [sp, #18]
    ldrb r0, [r4, #O_SVRES]
    and  r0, r0, #0x7F
    strb r0, [sp, #19]
    ldrh r0, [r4, #O_SVLAST]
    lsrs r1, r0, #7
    and  r1, r1, #0x7F
    strb r1, [sp, #20]
    and  r0, r0, #0x7F
    strb r0, [sp, #21]
    ldrb r0, [r4, #O_LDRES]
    and  r0, r0, #0x7F
    strb r0, [sp, #22]
    ldr  r1, =JR_IDX
    ldrh r0, [r1]
    lsrs r1, r0, #7
    and  r1, r1, #0x7F
    strb r1, [sp, #23]
    and  r0, r0, #0x7F
    strb r0, [sp, #24]
    ldr  r1, =JR_CNT
    ldr  r0, [r1]
    lsrs r1, r0, #7
    and  r1, r1, #0x7F
    strb r1, [sp, #25]
    and  r0, r0, #0x7F
    strb r0, [sp, #26]
    ldrb r0, [r4, #O_JRCNT]
    and  r0, r0, #0x7F
    strb r0, [sp, #27]
    ldrb r0, [r4, #O_JRRES]
    and  r0, r0, #0x7F
    strb r0, [sp, #28]
    ldrb r0, [r4, #O_BOOTRES]
    and  r0, r0, #0x7F
    strb r0, [sp, #29]
    mov  r0, sp
    movs r1, #30
    ldr  r3, =0x0801408D
    blx  r3                        @ FUN_0801408c(buf, len)
    add  sp, sp, #32
    pop  {r4, r5, r6, pc}
D_lane:                            @ r2 = slot
    push {r4, r5, r6, lr}
    sub  sp, sp, #24
    ldr  r4, =RAMB
    movs r0, #0x50
    strb r0, [sp, #0]
    strb r2, [sp, #1]
    lsls r5, r2, #4
    add  r5, r5, r4                @ lane base
    add  r6, sp, #2
    movs r3, #0
D_l:
    ldrh r0, [r5]
    adds r5, r5, #2
    lsrs r1, r0, #7
    and  r1, r1, #0x7F
    strb r1, [r6], #1              @ high 7 bits
    and  r0, r0, #0x7F
    strb r0, [r6], #1              @ low 7 bits
    adds r3, r3, #1
    cmp  r3, #8
    blt  D_l
    add  r0, r4, #O_BASE
    ldrh r0, [r0, r2, lsl #1]
    lsrs r1, r0, #7
    and  r1, r1, #0x7F
    strb r1, [r6], #1
    and  r0, r0, #0x7F
    strb r0, [r6], #1
    ldrh r0, [r4, #O_HASREC]
    lsrs r0, r0, r2
    and  r0, r0, #1
    strb r0, [r6], #1
    ldrh r0, [r4, #O_BASESET]
    lsrs r0, r0, r2
    and  r0, r0, #1
    strb r0, [r6], #1
    mov  r0, sp
    movs r1, #22                   @ cmd + slot + 16 lane + 2 base + 2 flags
    ldr  r3, =0x0801408D
    blx  r3
    add  sp, sp, #24
    pop  {r4, r5, r6, pc}
    .pool
    .endif                         @ DEBUG
