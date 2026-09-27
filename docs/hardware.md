<div align="center">
<img src="../assets/h-stack.svg" alt="Under the fur" width="100%"/>
</div>

# Luna hardware guide

Everything you need to build Luna's body: parts, wiring, joint map, calibration and firmware.
Back to the **[main README](../README.md)**.

---

## Hardware Bill of Materials

| Component         | Part / Module          | Role                                  | Source                  | Approx. Cost |
|-------------------|------------------------|---------------------------------------|-------------------------|-------------|
| Neural Unit       | `claude-neural-v3`     | Inference, instinct, personality      | OpenClaw store          | $89          |
| Vision Module     | `ClaudeVision-Lite`    | Face ID, object tracking, depth       | Taobao / eBay           | $34          |
| Tactile Fibers    | `SenseFur v2`          | 128-pt capacitive pressure + temp     | Hardware store + DIY    | $22          |
| Skeleton          | `FlexBone-X`           | 19-DOF aluminum + TPU frame           | 3D print + local hw     | $55          |
| Audio             | `PurrSynth v2.1`       | Real-time vocal synthesis             | Taobao                  | $14          |
| Battery           | `MoodCell 4400mAh`     | Adaptive discharge, mood signal pin   | eBay                    | $28          |
| Charging Base     | `RestPod v1`           | Qi wireless, GPIO dock sense          | Taobao                  | $17          |
| Skin              | Silicone casing        | Enclosure + tactile surface           | Local / Smooth-On       | $30          |
| Tail              | `TailSense v2`         | 3-DOF articulated tail + tip sensor   | 3D print + servo        | $12          |
| Compute           | Raspberry Pi 4B / 5    | Host OS, all firmware runtime         | Local electronics       | $55          |
| Servo Driver      | PCA9685 (Adafruit)     | 16-ch PWM, I2C 0x40                   | Local / Adafruit        | $8           |
| ADC               | MCP3008                | 8-ch SPI ADC for MoodCell SOC         | Local / Adafruit        | $4           |
| **Total**         |                        |                                       |                         | **~$368**    |

All non-specialty components (fasteners, wire, silicone, servo horns, heat shrink) can
be sourced from any local hardware store. The neural unit and ClaudeVision-Lite are the
only parts that require OpenClaw or specialized electronics suppliers.

See `bom.json` for exact part numbers, alternative suppliers, and minimum spec requirements.

---

## Directory Structure

```
luna-companion-cat/
  luna/                         python package (main source)
    firmware/
      neural_unit.py            UART framing, InstinctModel, MemoryInterface,
                                PersonalityInterface
    vision/
      pipeline.py               VisionPipeline, FaceDB, FaceEvent, ObjectEvent
    tactile/
      sensefur.py               SenseFurArray, SenseFurCalibrator, TactileEvent,
                                zone map
    personality/
      engine.py                 PersonalityEngine, AffectState, behavior table,
                                trigger valence map, trait drift
    locomotion/
      controller.py             LocomotionController, Joint, PCA9685 driver,
                                pose interpolation, gait playback
    audio/
      purrsynth.py              PurrSynth UART interface, clip library
    power/
      moodcell.py               MoodCell SOC monitor, RestPod charge manager,
                                MCP3008 ADC reader
    memory/
      store.py                  MemoryStore SQLite, trust score algorithm,
                                episodic + fact tables
    runtime.py                  Runtime process manager, subsystem wiring
    __main__.py                 entry point: python -m luna.runtime

  firmware/
    neural_unit.py              (mirror for direct import)
    README.md                   serial protocol spec, flash instructions
    openclaw_neural_v0.9.2.bin  pre-compiled neural unit firmware
    purrsynth_v2.1.bin          pre-compiled PurrSynth firmware

  hardware/
    README.md                   wiring diagrams, joint map, SenseFur wiring

  config/
    gaits/
      trot.yaml                 diagonal trot gait definition
      walk.yaml                 slow walk gait definition
    faces.db                    (generated) enrolled face embeddings
    sensefur_cal.bin            (generated) pressure baseline calibration
    personality_snapshot.json   (generated) periodic personality backup

  scripts/
    flash_neural.sh             flash OpenClaw firmware to neural unit
    flash_purrsynth.sh          flash PurrSynth firmware
    calibrate_sensefur.py       collect SenseFur baseline calibration
    enroll_face.py              enroll a new face into faces.db

  tests/
    unit/                       pytest unit tests (no hardware required)
      test_memory.py
      test_personality.py
      test_tactile.py
      test_firmware.py
    integration/                integration tests (requires hardware)
    hil/                        hardware-in-loop CI tests

  data/                         runtime data dir (SQLite DB lives here)
  logs/                         runtime logs
  .github/workflows/ci.yml      GitHub Actions: lint, unit tests, build check
  bom.json                      machine-readable bill of materials
  config.yaml                   main runtime configuration
  requirements.txt              Python dependencies
  setup.py                      package install
  .gitignore
```

---

## Quickstart

### Prerequisites

```bash
# Hardware: Raspberry Pi 4B or 5, 64-bit Raspberry Pi OS Bookworm
# Python 3.11+

uname -m           # expect: aarch64
python3 --version  # expect: 3.11.x or 3.12.x
i2cdetect -y 1     # should show devices at 0x40 (PCA9685) and 0x48 (SenseFur)
```

Enable I2C and SPI in raspi-config if not already done:

```bash
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0
sudo reboot
```

### Clone and Install

```bash
git clone https://github.com/nataliedevs/Ruby-Cat-Companion.git
cd luna-companion-cat
pip install -r requirements.txt
```

### Flash Firmware

```bash
# flash the neural unit (connected via USB-C to /dev/ttyUSB0)
./scripts/flash_neural.sh --port /dev/ttyUSB0 --verify

# flash PurrSynth audio chip (/dev/ttyUSB1)
./scripts/flash_purrsynth.sh --port /dev/ttyUSB1
```

### Calibrate SenseFur

Run this before first boot and after reassembling the skin:

```bash
python3 scripts/calibrate_sensefur.py --output config/sensefur_cal.bin
# do NOT touch Luna during calibration
# takes ~5 seconds at default 500 samples
```

### Enroll Faces

```bash
python3 scripts/enroll_face.py --name "Ada" --samples 30
# look at the camera while it captures samples
# UID is auto-generated; override with --uid if desired
```

### Run

```bash
# start all subsystems
python3 -m luna.runtime --config config.yaml

# or via installed entry point (after pip install -e .)
luna --config config.yaml
```

To run individual subsystems for debugging:

```bash
python3 -m luna.vision      &   # ClaudeVision-Lite only
python3 -m luna.tactile     &   # SenseFur reader only
python3 -m luna.personality &   # mood/memory daemon only
```

---

## Module Reference

### Neural Unit (OpenClaw Firmware)

The neural unit is a microcontroller board (Arduino Mega 2560 core) running OpenClaw
firmware. It communicates with the Pi over UART at 115200 baud using a simple framed
binary protocol.

```
Frame format: [0xAA] [LEN: 2 bytes BE] [CMD: 1 byte] [PAYLOAD: LEN bytes] [CRC8: 1 byte]
```

The neural unit exposes three logical subsystems: the instinct model, the memory
interface, and the personality interface. All three are accessible through the
`NeuralUnit` Python class.

```python
from luna.firmware.neural_unit import NeuralUnit

unit = NeuralUnit(port="/dev/ttyUSB0")
unit.connect()   # sends PING, verifies PONG, starts snapshot thread

# instinct model: behavioral drive weights
unit.instinct.set_drive("curiosity", weight=0.7)
unit.instinct.set_drive("social",    weight=0.85)
drives = unit.instinct.get_drives()
# {'curiosity': 0.7, 'social': 0.85, 'rest': 0.5, 'play': 0.5, 'hunt': 0.5, 'groom': 0.5}

# memory interface: episodic event encoding + trust query
unit.memory.encode(event="chin_scratch", uid="user_0", valence=+0.6)
trust = unit.memory.get_trust(uid="user_0")   # -> float in [0.0, 1.0]

# personality interface: trait snapshot + reset
snap = unit.personality.snapshot()
# PersonalitySnapshot(bold=0.62, playful=0.81, cautious=0.34,
#                     affectionate=0.74, curious=0.58, independent=0.45)

# DESTRUCTIVE: resets all traits and clears memory
# back up config/personality_snapshot.json first
unit.personality.reset()
```

Personality snapshots are flushed to `config/personality_snapshot.json` every
`snapshot_interval_s` seconds (default: 300) while the runtime is running.

Available drive names: `curiosity`, `social`, `rest`, `play`, `hunt`, `groom`.

Available UART commands (for low-level debugging):

```
CMD 0x01  SET_DRIVE
CMD 0x02  GET_DRIVES
CMD 0x10  ENCODE_EVENT
CMD 0x11  GET_TRUST
CMD 0x20  GET_PERSONALITY
CMD 0x21  RESET_PERSONALITY
CMD 0x30  PING
```

---

### ClaudeVision-Lite

The ClaudeVision-Lite module runs face recognition and object detection locally. It
connects via USB-C or MIPI CSI ribbon to the Pi. Face embeddings are stored in a local
SQLite database at `config/faces.db`. No embeddings leave the device.

Face recognition uses a HOG-based detector with a local 128-dimensional embedding
model. Depth estimation uses a MiDaS-small ONNX model, which gives relative depth
calibrated to approximate centimeters.

```python
from luna.vision.pipeline import VisionPipeline

vp = VisionPipeline(
    camera_index=0,
    resolution=(640, 480),
    fps=30,
    face_db="config/faces.db",
    confidence_threshold=0.82,
)

@vp.on_face
def handle_face(ev):
    # ev.uid:        str  -- face DB uid, or "unknown"
    # ev.label:      str  -- human-readable name
    # ev.bbox:       (x, y, w, h)
    # ev.depth_cm:   float
    # ev.confidence: float
    print(f"face={ev.label} depth={ev.depth_cm:.1f}cm conf={ev.confidence:.2f}")

@vp.on_object
def handle_object(ev):
    # ev.label, ev.bbox, ev.confidence, ev.depth_cm
    print(f"object={ev.label} conf={ev.confidence:.2f}")

vp.start()   # blocking; runs capture + inference loop
```

The `FaceDB` class manages enrollments directly:

```python
from luna.vision.pipeline import FaceDB
import numpy as np

db = FaceDB("config/faces.db")
db.enroll(uid="user_0", label="Ada", embedding=np.zeros(128, dtype=np.float32))
result = db.identify(embedding, threshold=0.82)
# returns (uid, label, similarity) or None
```

---

### SenseFur v2 Tactile Array

SenseFur v2 is a 128-point capacitive pressure and temperature mesh embedded in the
silicone skin. Each fiber is a capacitive node. An ATtiny84 multiplexer scans all 128
nodes and reports readings over I2C at up to 100Hz.

Zone layout:

```
SenseFur v2 fiber zone map (top view):
                           .------.
                          /  HEAD  \
              [zone: head] --+--+-- [zone: head]     fibers 0..31
                            |     |
               .---[back]---.     .---[back]---.     fibers 32..63
              |                                 |
              '--.                           .--'
                  \                         /
               [zone: flank]         [zone: flank]
                  |                         |
               .--'-------------------------'--.
              |            BELLY               |     fibers 64..95
               '--------------------------------'
                  |    |               |    |
              [paw_fl][paw_fr]     [paw_rl][paw_rr]  fibers 96..127
```

Zone index mapping:

```
head:   0..31
back:   32..63
belly:  64..95
paw_fl: 96..103
paw_fr: 104..111
paw_rl: 112..119
paw_rr: 120..127
```

Usage:

```python
from luna.tactile.sensefur import SenseFurArray, TactileEvent

sf = SenseFurArray(
    i2c_bus=1,
    i2c_address=0x48,
    sample_rate_hz=100,
    calibration_file="config/sensefur_cal.bin",
)

@sf.on_touch
def on_touch(ev: TactileEvent):
    # ev.zone:        str   -- e.g. "head", "belly", "paw_fl"
    # ev.pressure:    float -- 0.0 .. 1.0 (above baseline)
    # ev.temp_c:      float -- fiber surface temperature in Celsius
    # ev.duration_ms: int   -- how long the touch lasted
    # ev.fiber_idx:   int   -- raw fiber index 0..127
    print(f"touch zone={ev.zone} pressure={ev.pressure:.2f} temp={ev.temp_c:.1f}C")

sf.start()   # non-blocking, runs in background thread
```

Touch events only fire when pressure exceeds `PRESSURE_THRESHOLD` (0.08 by default)
and the touch lasts at least `TOUCH_MIN_MS` (50ms). This suppresses noise and
incidental contacts. Both thresholds are tunable as class attributes.

---

### Personality Engine

The PersonalityEngine manages Luna's affect state and personality trait vector.
Personality traits are floats in [0, 1] that drift slowly from interaction events.
Affect state (mood, energy) decays toward 0.5 neutral when no interactions occur.
Battery level from MoodCell feeds directly into the `energy` affect component.

Trigger events and their valence weights:

```
touch_chin       +0.35   (strong positive)
touch_head       +0.25
touch_back       +0.20
face_detected    +0.10
touch_paws       +0.10
touch_tail       +0.05
touch_belly      -0.15   (negative: most cats dislike belly touches)
warning_issued   -0.30
```

Trait drift effects per event:

```
touch_chin    -> affectionate +0.002, bold +0.001
touch_belly   -> cautious +0.002
touch_head    -> affectionate +0.001
play_session  -> playful +0.003, bold +0.001
```

Behavior recommendation table (checked in order, first match wins):

```
mood >= 0.65, energy >= 0.55, trust >= 0.60   -> playful_approach
mood >= 0.55, energy >= 0.45, trust >= 0.50   -> slow_explore
mood >= 0.40, energy >= 0.55, trust >= 0.40   -> alert_scan
mood >= 0.50, energy <= 0.50, trust >= 0.40   -> curl_up
mood >= 0.60, energy <= 0.70, trust >= 0.70   -> grooming_sit
mood <= 0.40                                  -> defensive_curl
fallback                                      -> idle_sit
```

```python
from luna.personality.engine import PersonalityEngine, AffectState
from luna.memory.store import MemoryStore

mem = MemoryStore(path="data/luna.db")
pe  = PersonalityEngine(memory=mem)

pe.update(
    trigger="chin_scratch",
    actor_uid="user_0",
    duration_ms=4200,
    battery_level=0.78,
)

affect = pe.get_affect()
# AffectState(mood=0.72, energy=0.78, trust_map={'user_0': 0.84})

behavior = pe.recommend_behavior(affect)
# 'playful_approach'

snap = pe.snapshot()
# {'bold': 0.52, 'playful': 0.53, 'cautious': 0.50, ...}
```

---

### LocomotionController (FlexBone-X)

The FlexBone-X skeleton has 19 total degrees of freedom: 16 body servos (MG996R) and
3 tail servos (MG90S). All servos are driven by a PCA9685 16-channel PWM controller
over I2C at address 0x40.

Joint map:

```
neck_yaw (ch 0)     neck_pitch (ch 1)
         \             /
          [HEAD UNIT]
               |
    shoulder_l (ch 2)   shoulder_r (ch 3)
          |                      |
      elbow_l (ch 4)         elbow_r (ch 5)
          |                      |
      wrist_l (ch 6)          wrist_r (ch 7)
               |
         [SPINE 4-DOF]
          spine_0 (ch 8)
          spine_1 (ch 9)
          spine_2 (ch 10)
          spine_3 (ch 11)
               |
      hip_l (ch 12)     hip_r (ch 13)
         |                     |
     knee_l (ch 14)        knee_r (ch 15)
               |
           [TAIL]
     tail_base_yaw (ch 16)
     tail_base_pitch (ch 17)
     tail_mid (ch 18)
     [TailSense capacitive sensor at tip -- GPIO input]
```

Pulse width formula: `pw = 500 + ((angle_deg + 90) / 180.0) * 2000` microseconds.
PCA9685 counts: `count = int(pw_us / 20000.0 * 4096)`.

```python
from luna.locomotion.controller import LocomotionController

loco = LocomotionController(
    servo_hz=50,
    max_torque_nm=2.5,
    gait_library="config/gaits/",
)
loco.enable()

# named pose with interpolation
loco.set_pose("sit", transition_ms=600)

# cyclic gait from YAML definition
loco.play_gait("trot", speed=0.5)

# raw joint access in radians
import math
loco.joints["neck_pitch"].set(math.radians(20))   # look up 20 degrees
loco.joints["tail_base_yaw"].set(math.radians(45))

# map personality behavior to locomotion
loco.execute_behavior("playful_approach")  # -> plays trot gait
loco.execute_behavior("curl_up")           # -> transitions to curl_up pose
```

Gait files are YAML in `config/gaits/`. Each file defines a list of keyframes and a
cycle period. The gait player interpolates between frames at the target speed. See
`config/gaits/trot.yaml` for the format.

---

### PurrSynth Audio

PurrSynth v2.1 is a dedicated audio synthesis chip on ATtiny84. It communicates over
UART with a simple text command protocol (commands terminated with CRLF).

Built-in clip library:

```
startup_chime       boot sequence chime
shutdown_purr       soft farewell purr
greeting_warm       chirpy meow for recognized faces (trust > 0.5)
greeting_cautious   soft trill for unknown faces
purr                continuous purr (loops until stop())
purr_loud           louder, more intense purr
chirp               single bird-like chirp
warning_hiss        defensive hiss
playful_trill       rolling trill during play
```

```python
from luna.audio.purrsynth import PurrSynth

ps = PurrSynth(port="/dev/ttyUSB1", volume=0.7, voice_profile="luna_v2")
ps.connect()

ps.play("purr", loop=True)
# ... time passes ...
ps.stop()

ps.play("chirp")
ps.set_volume(0.5)
print(ps.is_playing())   # True / False
```

UART protocol:

```
PLAY <clip_name> [LOOP]   start playback
STOP                       stop current playback
VOL <0-100>                set volume
PROFILE <name>             load voice profile
STATUS                     returns: PLAYING <clip> | IDLE
```

---

### MoodCell Power

MoodCell is a 3S LiPo pack (4400mAh) with a dedicated analog output pin that reflects
state of charge as a voltage from 0V to 3.3V. This is read via MCP3008 SPI ADC on
channel 0. The normalized SOC value (0.0 to 1.0) feeds directly into the `energy`
component of Luna's affect state.

RestPod charging is managed via two GPIO pins: one to enable the Qi transmitter coil
and one to sense whether Luna is docked on the base.

```python
from luna.power.moodcell import MoodCell

mc = MoodCell(
    restpod_charge_threshold=0.25,
    restpod_full_threshold=0.95,
    mood_signal_enabled=True,
    low_power_mode_threshold=0.10,
)

@mc.on_low
def handle_low(level):
    print(f"Battery low: {level:.1%} -- returning to base")

mc.start_monitor()
print(mc.level)     # current SOC float 0.0..1.0
print(mc.charging)  # True if currently charging
```

GPIO pinout (BCM):

```
GPIO17  -- MoodCell SOC analog input (via MCP3008 CH0)
GPIO18  -- RestPod charge enable output (HIGH = charging)
GPIO27  -- RestPod dock sense input (HIGH = on base, pulled down)
```

---

### MemoryStore

MemoryStore is the shared SQLite database used by both the neural unit interface and
the personality engine. It stores episodic events and semantic facts. Trust scores are
computed from episodic history using an exponential time-decay weighted sum.

Trust score formula:

```
trust(uid) = (1 + tanh(0.3 * sum(valence_i * exp(-LAMBDA * (now - t_i))))) / 2

where LAMBDA = 0.0001  (half-life ~1.9 hours)
Result is clamped to [0.0, 1.0]
Unknown uid returns 0.5 (neutral)
```

```python
from luna.memory.store import MemoryStore

mem = MemoryStore(path="data/luna.db")

mem.encode(uid="user_0", event="chin_scratch", valence=+0.7)
trust = mem.get_trust("user_0")   # -> float in [0.0, 1.0]

episodes = mem.get_recent_episodes("user_0", n=10)
# [Episode(uid='user_0', event='chin_scratch', valence=0.7, timestamp=1709...)]

mem.set_fact("owner_name", "Ada")
mem.get_fact("owner_name")   # -> "Ada"
mem.get_fact("no_such_key")  # -> None

mem.close()
```

Schema:

```sql
CREATE TABLE episodes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    uid       TEXT    NOT NULL,
    event     TEXT    NOT NULL,
    valence   REAL    NOT NULL,   -- -1.0 to +1.0
    timestamp REAL    NOT NULL    -- Unix epoch float
);
CREATE INDEX idx_ep_uid ON episodes(uid);

CREATE TABLE facts (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at REAL NOT NULL
);
```

---

## Configuration Reference

Full annotated `config.yaml`:

```yaml
neural_unit:
  port: /dev/ttyUSB0             # serial port for neural unit
  baud: 115200
  personality_persistence: true   # auto-snapshot personality to JSON
  snapshot_interval_s: 300        # flush every 5 minutes

vision:
  camera_index: 0                 # OpenCV camera index
  resolution: [640, 480]
  fps: 30
  face_db: config/faces.db        # SQLite face enrollment database
  confidence_threshold: 0.82      # minimum cosine similarity to ID a face
  depth_model: config/depth_lite.onnx
  track_max_objects: 8

tactile:
  i2c_bus: 1
  i2c_address: 0x48               # ATtiny84 mux I2C address
  sample_rate_hz: 100
  calibration_file: config/sensefur_cal.bin
  zones:
    head:  [0,  31]               # override zone ranges if your layout differs
    back:  [32, 63]
    belly: [64, 95]
    paws:  [96, 127]

audio:
  port: /dev/ttyUSB1
  baud: 115200
  voice_profile: luna_v2          # PurrSynth voice profile name
  volume: 0.7                     # 0.0 to 1.0

locomotion:
  servo_hz: 50                    # PCA9685 PWM frequency (Hz)
  max_torque_nm: 2.5              # soft torque limit for all joints
  gait_library: config/gaits/     # directory of gait YAML files
  home_pose_ms: 200               # transition time to neutral on enable

personality:
  db: data/luna.db                # SQLite path for MemoryStore
  trait_drift_rate: 0.001         # trait change per interaction event
  mood_decay_rate: 0.0005         # mood decay per second toward 0.5 neutral
  trust_decay_rate: 0.0001        # trust decay per second without interaction

power:
  restpod_charge_threshold: 0.25  # begin charging below 25% SOC
  restpod_full_threshold: 0.95    # stop charging above 95% SOC
  mood_signal_enabled: true       # battery level modulates energy affect
  low_power_mode_threshold: 0.10  # reduce vision fps + servo torque below 10%

logging:
  level: INFO
  file: logs/luna.log
  max_bytes: 10485760             # 10 MB per log file
  backup_count: 5
```

---

## Gait Library

Gaits are defined as YAML files in `config/gaits/`. Each file specifies a cycle period
and a list of keyframes. Each keyframe is a dict of joint name to target angle in
degrees. The gait player cycles through frames at `period_s / num_frames` per frame,
scaled by the `speed` argument.

Minimal gait format:

```yaml
period_s: 0.8           # full cycle duration at speed=1.0

poses:                  # optional named poses referenced in gait
  trot_home:
    hip_l: 0
    knee_l: 90

frames:
  - hip_l: -20
    knee_l: 60
    hip_r: 20
    knee_r: 100
  - hip_l: 0
    knee_l: 90
    hip_r: 0
    knee_r: 90
  - hip_l: 20
    knee_l: 100
    hip_r: -20
    knee_r: 60
```

Built-in gaits: `trot`, `walk`. Add your own YAML files to `config/gaits/` and call
`loco.play_gait("your_gait_name")`.

---

## Face Enrollment

```bash
# enroll with auto-generated UID
python3 scripts/enroll_face.py --name "Ada" --samples 30

# enroll with explicit UID
python3 scripts/enroll_face.py --name "Max" --uid user_max --samples 50

# use a different camera
python3 scripts/enroll_face.py --name "Ada" --camera 1 --samples 30
```

The script captures N frames, computes face embeddings for each, averages them, and
normalizes the result before storing in `config/faces.db`. More samples gives a more
robust embedding. 30 is usually sufficient in good lighting; use 50+ in variable light.

Luna will display "greeting_warm" audio and a head-lean pose toward any recognized
face with trust > 0.5. Unknown faces get "greeting_cautious" and an alert scan.

---

## SenseFur Calibration

SenseFur calibration captures the resting baseline pressure at each of the 128 fiber
nodes and saves a binary file used to zero-out the readings at runtime.

```bash
# standard calibration (500 samples, ~5 seconds)
python3 scripts/calibrate_sensefur.py --output config/sensefur_cal.bin

# longer calibration for noisy environments
python3 scripts/calibrate_sensefur.py --output config/sensefur_cal.bin --samples 1000

# run without hardware (produces near-zero baseline for testing)
python3 scripts/calibrate_sensefur.py --output config/sensefur_cal.bin --simulate
```

Recalibrate whenever:
- You reassemble the silicone skin
- Luna moves to a significantly different temperature environment
- You see spurious touch events firing with no contact

---

## Flashing Firmware

### Neural Unit

```bash
./scripts/flash_neural.sh --port /dev/ttyUSB0 --verify
```

Flags:
- `--port`     serial port (default: /dev/ttyUSB0)
- `--verify`   read back and verify flash after write
- `--dry-run`  print what would happen without writing

The script uses `avrdude` with the Arduino bootloader protocol. The neural unit must
be connected via USB-C before running. If avrdude is not installed:

```bash
sudo apt install avrdude
```

### PurrSynth

```bash
./scripts/flash_purrsynth.sh --port /dev/ttyUSB1
```

Uses USBasp programmer. The ATtiny84 is on the PurrSynth PCB with ISP header exposed.

---

## Testing

### Unit Tests (no hardware required)

```bash
pip install pytest pytest-mock
pytest tests/unit/ -v
```

The unit tests mock all hardware interfaces (serial, I2C, GPIO, ADC). They cover:
- `test_memory.py` -- trust score algorithm, episodic encoding, fact store
- `test_personality.py` -- affect update, mood decay, behavior recommendation, trait drift
- `test_tactile.py` -- zone mapping, fiber index coverage, event threshold logic
- `test_firmware.py` -- CRC8 implementation, frame parsing, PersonalitySnapshot

### Integration Tests (requires connected hardware)

```bash
pytest tests/integration/ --hardware
```

Integration tests connect to real hardware and verify end-to-end subsystem behavior.
They require all devices to be connected and firmware to be flashed.

### Hardware-in-Loop (CI/CD)

```bash
pytest tests/hil/ --hil-host 192.168.1.42
```

The HIL tests run the full runtime against a real Luna unit on a test bench. Used in
the CI/CD pipeline via GitHub Actions self-hosted runner.

---

## Wiring

### I2C Bus (bus 1, BCM pins 2/3)

```
RPi SDA (pin 3) ---- PCA9685 SDA (addr 0x40)  -- servo driver
                 ---- ATtiny84 SDA (addr 0x48)  -- SenseFur mux
RPi SCL (pin 5) ---- PCA9685 SCL
                 ---- ATtiny84 SCL
RPi 3.3V        ---- PCA9685 VCC
                 ---- ATtiny84 VCC
RPi GND         ---- PCA9685 GND
                 ---- ATtiny84 GND
```

> External 4.7k pull-up resistors on SDA and SCL are recommended if I2C runs longer
> than 20cm or if you have more than 2 devices on the bus.

### SPI Bus (SPI0, BCM pins 10/9/11/8)

```
RPi MOSI (pin 19) ---- MCP3008 Din
RPi MISO (pin 21) ---- MCP3008 Dout
RPi SCLK (pin 23) ---- MCP3008 CLK
RPi CE0  (pin 24) ---- MCP3008 CS/SHDN
RPi 3.3V          ---- MCP3008 VDD + VREF
RPi GND           ---- MCP3008 AGND + DGND
MCP3008 CH0       ---- MoodCell analog SOC output
```

### GPIO

```
BCM 18 (pin 12) ---- RestPod charge enable (active HIGH, 3.3V signal)
BCM 27 (pin 13) ---- RestPod dock sense input (pull-down, HIGH = docked)
```

### UART

```
RPi UART0 TX (pin 8)  ---- Neural Unit RX
RPi UART0 RX (pin 10) ---- Neural Unit TX
/dev/ttyUSB0          ---- Neural Unit USB-C (alternative via CH340 adapter)
/dev/ttyUSB1          ---- PurrSynth UART
```

### PCA9685 Servo Channels

```
CH 0   neck_yaw
CH 1   neck_pitch
CH 2   shoulder_l
CH 3   shoulder_r
CH 4   elbow_l
CH 5   elbow_r
CH 6   wrist_l
CH 7   wrist_r
CH 8   spine_0
CH 9   spine_1
CH 10  spine_2
CH 11  spine_3
CH 12  hip_l
CH 13  hip_r
CH 14  knee_l
CH 15  knee_r
CH 16  tail_base_yaw
CH 17  tail_base_pitch
CH 18  tail_mid
```

---

## Sourcing and Build Notes

### What you can get locally

Fasteners (M2/M3 screws, standoffs), hookup wire, heat shrink, silicone (Smooth-On
Ecoflex 00-30 or equivalent), the Raspberry Pi (check rpilocator.com for stock), the
PCA9685 breakout, the MCP3008, and MG996R / MG90S servos are all generic parts
available at local electronics and hardware stores or from general-purpose platforms
like Taobao, eBay, or AliExpress.

### What requires specific suppliers

The Claude Neural Unit v3 and ClaudeVision-Lite are OpenClaw-specific modules. See
[openclaw.dev](https://openclaw.dev) for availability and shipping. The PurrSynth
board is a custom PCB but the design files are in the companion hardware repo
([openclaw/luna-hardware](https://github.com/openclaw/luna-hardware)) if you want to
fab it yourself at JLCPCB or similar.

### SenseFur construction

SenseFur v2 is a DIY component. The full construction guide is in
`hardware/sensefur/BUILD.md` (in the hardware repo). The short version: it is a 16x8
grid of conductive thread nodes embedded in a fabric backing, scanned by an ATtiny84
running custom firmware. All materials (conductive thread, capacitive sensing fabric,
ATtiny84 boards) are available from hobby electronics suppliers. Budget ~3 hours for
assembly and ~1 hour for soldering.

### 3D printing

All structural parts for FlexBone-X, the tail assembly, and the eye housing are 3D
printable. Use PETG or PLA+ for rigid parts and TPU (95A) for joint flexures. Print
TPU flexures at 95% infill, 2 perimeters. Full print files and assembly instructions
are in the hardware repo.

### Silicone skin

The skin is cast from a two-part mold. Mold files are in the hardware repo. Use
Smooth-On Ecoflex 00-30 or equivalent Shore 00-30 silicone. Mix 1:1 by volume, add
pigment to taste, degas under vacuum if available (optional but reduces bubbles), and
pour into the mold. Cure time is 4 hours at room temperature. The SenseFur fiber array
sits between the inner and outer skin layers and is encapsulated during the pour.

---

