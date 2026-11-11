// Aggressive pre-analysis recovery for a raw Cortex-M image.
// 1. Seeds the vector table handlers (like SeedCortexM).
// 2. Scans undefined executable bytes for Thumb function prologues
//    (push {..,lr} = 0xB5xx, or stmdb sp!,{..,lr} = 0xE92D with lr set)
//    and defines a function at each.
// 3. Follows code-pointer tables: any aligned word that points into the
//    code block with bit0 set is treated as a function pointer.
// Auto-analysis then propagates calls and data refs.
// @category NightSky
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;

public class RecoverCortexM extends GhidraScript {
    long base, end;
    Memory mem;

    public void run() throws Exception {
        mem = currentProgram.getMemory();
        base = currentProgram.getImageBase().getOffset();
        end = base + mem.getSize();
        java.util.LinkedHashSet<Long> targets = new java.util.LinkedHashSet<>();

        // 1. vector table
        Address b = currentProgram.getImageBase();
        for (int i = 1; i < 128; i++) {
            Address slot = b.add(4L * i);
            if (!mem.contains(slot)) break;
            long v = Integer.toUnsignedLong(mem.getInt(slot));
            if (v != 0) addCode(targets, v);
        }
        // 3. code-pointer tables: scan every aligned word
        for (long a = base; a + 4 <= end; a += 4) {
            try {
                long v = Integer.toUnsignedLong(mem.getInt(b.getNewAddress(a)));
                if ((v & 1) == 1) addCode(targets, v);
            } catch (Exception e) { /* unreadable word, skip */ }
        }
        // 2. Thumb prologues in the whole image (cheap, auto-analysis dedups)
        for (long a = base; a + 4 <= end; a += 2) {
            try {
                int h = mem.getShort(b.getNewAddress(a)) & 0xFFFF;
                boolean prologue = (h & 0xFF00) == 0xB500;        // push {..,lr}
                if (!prologue && h == 0xE92D) {                    // push.w
                    int h2 = mem.getShort(b.getNewAddress(a + 2)) & 0xFFFF;
                    prologue = (h2 & 0x4000) != 0;                 // lr in list
                }
                if (prologue) targets.add(a);
            } catch (Exception e) { /* skip */ }
        }

        int ok = 0;
        for (long t : targets) {
            Address a = b.getNewAddress(t);
            try {
                if (getInstructionAt(a) == null) disassemble(a);
                if (getFunctionAt(a) == null) createFunction(a, null);
                ok++;
            } catch (Exception e) { /* keep going */ }
        }
        println("RecoverCortexM: defined ~" + ok + " function candidates from "
                + targets.size() + " targets");
    }

    void addCode(java.util.Set<Long> set, long v) {
        long code = v & ~1L;
        if (code >= base && code < end) set.add(code);
    }
}
