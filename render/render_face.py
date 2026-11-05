"""Render Madam Ji talking-head clips with InfiniteTalk (Wan2GP). Runs in the Wan2GP venv.
Usage: python render_face.py tasks.json   (tasks = [{"audio": wav16k, "out": mp4, "seed": int}])
Fixed recipe = the look approved on 5 Nov: one photo, 480x832, lightx2v 4-step accelerator."""
import json, sys, time, shutil, glob, os
from pathlib import Path
sys.path.insert(0, "/tmp/Wan2GP")
from shared.api import init
PHOTO = os.environ.get("MADAMJI_PHOTO", "/tmp/it/madamji.jpg")
PROMPT = "A warm Indian female teacher in a mustard saree talks to the camera in a classroom, natural head movement, friendly expression"
LORA = "https://huggingface.co/DeepBeepMeep/Wan2.1/resolve/main/loras_accelerators/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors"
tasks = json.load(open(sys.argv[1]))
s = init(root=Path("/tmp/Wan2GP"), cli_args=["--attention", "sdpa", "--profile", "4"])
for k, tk in enumerate(tasks):
    d = s.get_default_settings("infinitetalk")
    d.update(prompt=PROMPT, resolution="480x832", video_length=f"{tk['seconds']:.2f}s",
             image_prompt_type="S", image_start=PHOTO, image_refs=[PHOTO],
             audio_prompt_type="A", audio_guide=tk["audio"], seed=int(tk.get("seed", 42)),
             num_inference_steps=4, activated_loras=[LORA], loras_multipliers="1",
             guidance_scale=1, audio_guidance_scale=1, guidance_phases=1)
    before = set(glob.glob("/tmp/Wan2GP/outputs/**/*.mp4", recursive=True))
    t = time.time(); job = s.submit_task(d); last = ""
    for ev in job.events.iter(timeout=1.0):
        if ev.kind == "progress":
            msg = f"{ev.data.phase} {ev.data.current_step}/{ev.data.total_steps}"
            if msg != last: print(f"[task {k} {time.time()-t:5.0f}s] {msg}", flush=True); last = msg
    r = job.result()
    if r.success:
        new = sorted(set(glob.glob("/tmp/Wan2GP/outputs/**/*.mp4", recursive=True)) - before, key=os.path.getmtime)
        src = new[-1] if new else r.generated_files[-1]
        shutil.copy(src, tk["out"]); print(f"TASK_OK {k} {tk['out']} {time.time()-t:.0f}s", flush=True)
    else:
        print(f"TASK_FAIL {k} {[e.message for e in r.errors]}", flush=True)
