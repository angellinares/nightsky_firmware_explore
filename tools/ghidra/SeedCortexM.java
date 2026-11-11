// Pre-analysis seed for a raw Cortex-M image loaded at its base address.
// Reads the vector table at the image base: word0 = initial SP (ignored),
// words 1..N = exception/IRQ handlers (thumb, odd). Disassembles each and
// marks it as an entry point so auto-analysis builds a real call graph.
// @category NightSky
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;

public class SeedCortexM extends GhidraScript {
    public void run() throws Exception {
        Memory mem = currentProgram.getMemory();
        Address base = currentProgram.getImageBase();
        int vectors = 128;               // SP + 15 system + up to ~112 IRQ
        java.util.LinkedHashSet<Long> targets = new java.util.LinkedHashSet<>();
        for (int i = 1; i < vectors; i++) {
            Address slot = base.add(4L * i);
            if (!mem.contains(slot)) break;
            long v = Integer.toUnsignedLong(mem.getInt(slot));
            if (v == 0) continue;
            long code = v & ~1L;         // strip thumb bit
            if (code >= base.getOffset() && code < base.getOffset() + mem.getSize())
                targets.add(code);
        }
        int done = 0;
        for (long t : targets) {
            Address a = base.getNewAddress(t);
            try {
                disassemble(a);
                createFunction(a, null);
                addEntryPoint(a);
                done++;
            } catch (Exception e) { /* keep going */ }
        }
        println("SeedCortexM: seeded " + done + " handler entries from " + targets.size() + " vectors");
    }
}
