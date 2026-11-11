// Ghidra post-analysis export for the NightSky firmware.
// Decompiles every function to decomp/<entry>_<name>.c and writes
// functions.jsonl (entry, name, size, callers, callees, string/data refs)
// plus refs.csv (from_addr,to_addr,kind) for building a SQLite index.
//
// Run headless, e.g.:
//   analyzeHeadless PROJDIR proj -process fwu_v107.bin \
//     -postScript ExportFw.java OUTDIR
// @category NightSky
import java.io.*;
import java.util.*;
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.data.StringDataInstance;
import ghidra.program.model.mem.MemoryAccessException;

public class ExportFw extends GhidraScript {
    public void run() throws Exception {
        String outDir = (getScriptArgs().length > 0) ? getScriptArgs()[0]
                        : (System.getProperty("java.io.tmpdir") + "/fwexport");
        File decompDir = new File(outDir, "decomp");
        decompDir.mkdirs();
        PrintWriter fj = new PrintWriter(new FileWriter(new File(outDir, "functions.jsonl")));
        PrintWriter rc = new PrintWriter(new FileWriter(new File(outDir, "refs.csv")));
        rc.println("from,to,kind");

        DecompInterface dec = new DecompInterface();
        DecompileOptions opts = new DecompileOptions();
        dec.setOptions(opts);
        dec.openProgram(currentProgram);

        Listing listing = currentProgram.getListing();
        ReferenceManager rm = currentProgram.getReferenceManager();
        FunctionManager fm = currentProgram.getFunctionManager();

        int n = 0;
        FunctionIterator it = fm.getFunctions(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Function f = it.next();
            long entry = f.getEntryPoint().getOffset();
            String name = f.getName();
            long size = f.getBody().getNumAddresses();

            // callers / callees
            StringBuilder callers = new StringBuilder();
            for (Function c : f.getCallingFunctions(monitor))
                callers.append(String.format("\"%x\",", c.getEntryPoint().getOffset()));
            StringBuilder callees = new StringBuilder();
            for (Function c : f.getCalledFunctions(monitor))
                callees.append(String.format("\"%x\",", c.getEntryPoint().getOffset()));

            // data/string refs out of this function
            StringBuilder strs = new StringBuilder();
            AddressSetView body = f.getBody();
            for (Address a : body.getAddresses(true)) {
                for (Reference r : rm.getReferencesFrom(a)) {
                    Address to = r.getToAddress();
                    rc.println(String.format("%x,%x,%s", a.getOffset(), to.getOffset(), r.getReferenceType().getName()));
                    Data d = listing.getDataAt(to);
                    if (d != null && d.hasStringValue()) {
                        String s = d.getDefaultValueRepresentation();
                        strs.append("\"").append(json(s)).append("\",");
                    }
                }
            }

            fj.println(String.format(
                "{\"entry\":\"%x\",\"name\":\"%s\",\"size\":%d,\"callers\":[%s],\"callees\":[%s],\"strings\":[%s]}",
                entry, json(name), size, trim(callers), trim(callees), trim(strs)));

            // decompile
            DecompileResults dr = dec.decompileFunction(f, 60, monitor);
            String c = (dr != null && dr.decompileCompleted()) ? dr.getDecompiledFunction().getC()
                       : "// decompile failed: " + (dr != null ? dr.getErrorMessage() : "null");
            File cf = new File(decompDir, String.format("%08x_%s.c", entry, safe(name)));
            try (PrintWriter p = new PrintWriter(new FileWriter(cf))) { p.print(c); }
            n++;
            if (n % 200 == 0) println("decompiled " + n);
        }
        fj.close(); rc.close();
        println("exported " + n + " functions to " + outDir);
    }
    String trim(StringBuilder b){ int l=b.length(); return l>0 ? b.substring(0,l-1) : ""; }
    String json(String s){ return s.replace("\\","\\\\").replace("\"","\\\""); }
    String safe(String s){ return s.replaceAll("[^A-Za-z0-9_.-]","_"); }
}
