//Exports what ViWo keeps of a headless Ghidra analysis (doc 6.3): functions.csv,
//decompiled.c, strings.txt and symbols.tsv, into the folder given as the script argument.
//@category ViWo
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Symbol;
import java.io.File;
import java.io.PrintWriter;

public class ViwoExport extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        File out = new File(args.length > 0 ? args[0] : ".");
        out.mkdirs();
        functionsAndCode(out);
        strings(out);
        symbols(out);
        println("ViWo export done: " + out);
    }

    private void functionsAndCode(File out) throws Exception {
        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        try (PrintWriter f = new PrintWriter(new File(out, "functions.csv"), "UTF-8");
             PrintWriter c = new PrintWriter(new File(out, "decompiled.c"), "UTF-8")) {
            f.println("address,name,size");
            for (Function fn : currentProgram.getFunctionManager().getFunctions(true)) {
                if (monitor.isCancelled()) {
                    break;
                }
                f.println(fn.getEntryPoint() + "," + fn.getName() + "," + fn.getBody().getNumAddresses());
                DecompileResults r = decomp.decompileFunction(fn, 60, monitor);
                if (r != null && r.decompileCompleted()) {
                    c.println("// " + fn.getEntryPoint() + " " + fn.getName());
                    c.println(r.getDecompiledFunction().getC());
                }
            }
        } finally {
            decomp.dispose();
        }
    }

    private void strings(File out) throws Exception {
        try (PrintWriter s = new PrintWriter(new File(out, "strings.txt"), "UTF-8")) {
            for (Data data : currentProgram.getListing().getDefinedData(true)) {
                if (data.hasStringValue()) {
                    s.println(data.getAddress() + "\t" + data.getDefaultValueRepresentation());
                }
            }
        }
    }

    private void symbols(File out) throws Exception {
        try (PrintWriter s = new PrintWriter(new File(out, "symbols.tsv"), "UTF-8")) {
            for (Symbol sym : currentProgram.getSymbolTable().getAllSymbols(false)) {
                s.println(sym.getAddress() + "\t" + sym.getSymbolType() + "\t" + sym.getName(true));
            }
        }
    }
}
