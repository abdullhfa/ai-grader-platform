/**
 * PRO Scratch VM runner — green flag, record variables, broadcasts, say outputs.
 * Usage: node run_scratch_vm.mjs <path-to.sb3> [maxSteps]
 *
 * Requires: npm install scratch-vm scratch-svg-renderer (in this scripts folder)
 */
import fs from "fs";
import path from "path";
import { createRequire } from "module";

const require = createRequire(import.meta.url);

const sb3Path = process.argv[2];
const maxSteps = parseInt(process.argv[3] || "5000", 10);

const result = {
  ran: false,
  variables: [],
  broadcasts: [],
  outputs: [],
  events: [],
  steps_executed: 0,
  error: null,
};

async function main() {
  if (!sb3Path || !fs.existsSync(sb3Path)) {
    result.error = "sb3_not_found";
    console.log(JSON.stringify(result));
    process.exit(1);
  }

  let VirtualMachine;
  try {
    VirtualMachine = require("scratch-vm");
  } catch (e) {
    result.error = "scratch_vm_not_installed";
    console.log(JSON.stringify(result));
    process.exit(0);
  }

  const vm = new VirtualMachine();
  const buffer = fs.readFileSync(sb3Path);
  await vm.loadProject(buffer);

  const varSnapshots = new Map();
  const recordVars = () => {
    for (const target of vm.runtime.targets) {
      if (!target.variables) continue;
      for (const [id, variable] of Object.entries(target.variables)) {
        const key = `${target.getName?.() || target.name}:${variable.name}`;
        const val = variable.value;
        const prev = varSnapshots.get(key);
        if (prev !== val) {
          varSnapshots.set(key, val);
          result.variables.push({ name: key, value: val });
        }
      }
    }
  };

  vm.runtime.on("PROJECT_START", () => {
    result.events.push({ type: "PROJECT_START" });
  });
  vm.runtime.on("PROJECT_RUN_START", () => {
    result.events.push({ type: "PROJECT_RUN_START" });
  });
  vm.runtime.on("PROJECT_RUN_STOP", () => {
    result.events.push({ type: "PROJECT_RUN_STOP" });
  });
  if (vm.runtime.on) {
    vm.runtime.on("SAY", (_target, _type, text) => {
      result.outputs.push({ kind: "say", text: String(text).slice(0, 200) });
    });
    vm.runtime.on("QUESTION", (_target, question) => {
      result.outputs.push({ kind: "question", text: String(question).slice(0, 200) });
    });
  }

  const originalBroadcast = vm.runtime.startHats?.bind(vm.runtime);
  if (originalBroadcast) {
    vm.runtime.startHats = (opcode, fields) => {
      if (opcode === "event_whenbroadcastreceived" && fields?.BROADCAST_OPTION) {
        result.broadcasts.push({ message: fields.BROADCAST_OPTION, opcode });
      }
      return originalBroadcast(opcode, fields);
    };
  }

  vm.greenFlag();
  result.ran = true;

  const tickMs = 16;
  const maxTicks = Math.min(maxSteps, 8000);
  for (let i = 0; i < maxTicks; i++) {
    vm.runtime._step();
    if (i % 10 === 0) recordVars();
    await new Promise((r) => setTimeout(r, 0));
  }
  recordVars();
  result.steps_executed = maxTicks;

  // Stage snapshot — lightweight visual evidence from VM (sprites/targets after run)
  try {
    const targets = vm.runtime.targets || [];
    result.stage_snapshot = {
      target_count: targets.length,
      sprite_count: targets.filter((t) => !t.isStage).length,
      sprite_names: targets
        .filter((t) => !t.isStage)
        .map((t) => t.getName?.() || t.name || "")
        .filter(Boolean)
        .slice(0, 24),
      stage_running: Boolean(vm.runtime.threads?.length),
    };
  } catch (_e) {
    result.stage_snapshot = null;
  }

  vm.stopAll();
  console.log(JSON.stringify(result));
}

main().catch((err) => {
  result.error = String(err.message || err).slice(0, 300);
  console.log(JSON.stringify(result));
  process.exit(0);
});
