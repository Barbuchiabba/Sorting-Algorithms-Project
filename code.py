import math
import queue
import random
import threading
import time
import tkinter as tk
from array import array
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import ttk
from typing import Callable, Dict, Generator, List, Optional

Highlight = Dict[int, str]
StepGenerator = Generator[Dict[str, object], None, None]


class SoundEngine:
    """
    Small cross-platform-ish sound engine.

    Best experience:
        pip install simpleaudio

    Fallback:
        Tk bell
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.enabled = True
        self.sample_rate = 22050
        self.note_queue = queue.Queue(maxsize=96)
        self.last_enqueue = 0.0
        self.cache = {}
        self.simpleaudio = None

        try:
            import simpleaudio  # type: ignore
            self.simpleaudio = simpleaudio
        except Exception:
            self.simpleaudio = None

        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def clear(self) -> None:
        while not self.note_queue.empty():
            try:
                self.note_queue.get_nowait()
            except queue.Empty:
                break

    def _worker_loop(self) -> None:
        while True:
            job = self.note_queue.get()

            if not self.enabled:
                continue

            kind = job[0]

            if kind == "note":
                _, freq, duration = job
                if self.simpleaudio is not None:
                    audio = self._make_note(freq, duration)
                    try:
                        play_obj = self.simpleaudio.play_buffer(audio, 1, 2, self.sample_rate)
                        play_obj.wait_done()
                    except Exception:
                        pass
                else:
                    self.root.after(0, self.root.bell)
                    time.sleep(min(duration, 0.03))

            elif kind == "finish":
                _, freqs = job
                if self.simpleaudio is not None:
                    for freq in freqs:
                        if not self.enabled:
                            break
                        audio = self._make_note(freq, 0.055)
                        try:
                            play_obj = self.simpleaudio.play_buffer(audio, 1, 2, self.sample_rate)
                            play_obj.wait_done()
                        except Exception:
                            pass
                else:
                    for _ in freqs:
                        if not self.enabled:
                            break
                        self.root.after(0, self.root.bell)
                        time.sleep(0.05)

    def _make_note(self, freq: float, duration: float) -> bytes:
        key = (round(freq, 1), round(duration, 4))
        if key in self.cache:
            return self.cache[key]

        sr = self.sample_rate
        frames = max(1, int(sr * duration))
        attack = max(1, int(frames * 0.05))
        decay = max(1, int(frames * 0.10))
        release = max(1, int(frames * 0.18))
        sustain = max(1, frames - attack - decay - release)
        sustain_level = 0.55

        data = array("h")
        amp = 14500

        for i in range(frames):
            t = i / sr

            p1 = (t * freq) % 1.0
            tri1 = 4.0 * abs(p1 - 0.5) - 1.0

            p2 = (t * (freq * 2.0)) % 1.0
            tri2 = 4.0 * abs(p2 - 0.5) - 1.0

            wave = 0.86 * tri1 + 0.14 * tri2

            if i < attack:
                env = i / attack
            elif i < attack + decay:
                pos = (i - attack) / decay
                env = 1.0 - (1.0 - sustain_level) * pos
            elif i < attack + decay + sustain:
                env = sustain_level
            else:
                pos = (i - attack - decay - sustain) / max(1, release)
                env = sustain_level * max(0.0, 1.0 - pos)

            sample = int(max(-32767, min(32767, wave * env * amp)))
            data.append(sample)

        audio = data.tobytes()
        if len(self.cache) > 256:
            self.cache.clear()
        self.cache[key] = audio
        return audio

    def _value_to_freq(self, value: float, max_value: float) -> float:
        if max_value <= 0:
            return 440.0
        ratio = max(0.0, min(1.0, value / max_value))
        return 120.0 + ratio * (1212.0 - 120.0)

    def play_compare(self, a: float, b: float, max_value: float, speed: int) -> None:
        if not self.enabled:
            return

        now = time.perf_counter()
        min_gap = max(0.004, 0.018 - speed * 0.0005)
        if now - self.last_enqueue < min_gap:
            return
        self.last_enqueue = now

        freq = self._value_to_freq((a + b) / 2.0, max_value)
        duration = max(0.010, 0.025 - speed * 0.0005)

        if self.note_queue.qsize() < 20:
            try:
                self.note_queue.put_nowait(("note", freq, duration))
            except queue.Full:
                pass

    def play_finish(self, max_value: float) -> None:
        if not self.enabled:
            return

        freqs = [
            self._value_to_freq(max_value * 0.35, max_value),
            self._value_to_freq(max_value * 0.55, max_value),
            self._value_to_freq(max_value * 0.78, max_value),
            self._value_to_freq(max_value * 1.00, max_value),
        ]
        try:
            self.note_queue.put_nowait(("finish", freqs))
        except queue.Full:
            pass


@dataclass
class Racer:
    name: str
    description: str
    algorithm: Callable[["SortingTournamentApp", "Racer"], StepGenerator]
    array: List[int] = field(default_factory=list)
    comparisons: int = 0
    swaps: int = 0
    finished: bool = False
    finish_time_ms: Optional[int] = None
    rank: Optional[int] = None
    generator: Optional[StepGenerator] = None
    canvas: Optional[tk.Canvas] = None
    cmp_var: Optional[tk.StringVar] = None
    swap_var: Optional[tk.StringVar] = None
    time_var: Optional[tk.StringVar] = None
    status_var: Optional[tk.StringVar] = None


class SortingTournamentApp:
    COLORS = {
        "bg": "#030703",
        "surface": "#071007",
        "surface2": "#0b170b",
        "surface3": "#0f1f0f",
        "border": "#19b34d",
        "accent": "#39ff14",
        "accent2": "#7fff7f",
        "text": "#b7ffbf",
        "muted": "#6fd07f",
        "compare": "#d9ff3b",
        "swap": "#00ffaa",
        "pivot": "#7affd4",
        "sorted": "#39ff14",
        "default": "#149b45",
        "winner": "#d4ff00",
        "button_bg": "#071007",
        "button_active": "#112711",
        "danger": "#ff5c5c",
    }

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Sorting Olympics // Hackathon Edition")
        self.root.geometry("1530x920")
        self.root.minsize(1200, 760)
        self.root.configure(bg=self.COLORS["bg"])

        self.running = False
        self.after_id = None
        self.start_time = 0.0
        self.finished_count = 0
        self.current_mode = ""
        self.current_algorithms: List[str] = []
        self.racers: List[Racer] = []

        self.size_var = tk.IntVar(value=42)
        self.speed_var = tk.IntVar(value=18)
        self.sound_var = tk.BooleanVar(value=True)
        self.algo1_var = tk.StringVar()
        self.algo2_var = tk.StringVar()
        self.home_status_var = tk.StringVar(value="> SELECT TWO ALGORITHMS FOR A 1v1, OR RUN THE FULL 6-ALGORITHM EVENT.")
        self.winner_var = tk.StringVar(value="WINNER: ---")
        self.results_var = tk.StringVar(value="RESULTS: waiting for race initialization...")

        self.sound = SoundEngine(self.root)

        self.algorithms = {
            "Bubble Sort": {
                "desc": "Simple and recognizable O(n²) baseline.",
                "fn": self.bubble_sort_steps,
            },
            "Selection Sort": {
                "desc": "Finds the minimum each pass and places it up front.",
                "fn": self.selection_sort_steps,
            },
            "Insertion Sort": {
                "desc": "Fast on small or nearly sorted arrays.",
                "fn": self.insertion_sort_steps,
            },
            "Merge Sort": {
                "desc": "Consistent divide-and-conquer O(n log n).",
                "fn": self.merge_sort_steps,
            },
            "Quick Sort": {
                "desc": "Classic fast sorter with strong average performance.",
                "fn": self.quick_sort_steps,
            },
            "Heap Sort": {
                "desc": "Heap-powered O(n log n) with no extra merge buffer.",
                "fn": self.heap_sort_steps,
            },
        }

        names = list(self.algorithms.keys())
        self.algo1_var.set(names[0])
        self.algo2_var.set(names[4])

        self.logo_image = None

        self._configure_styles()
        self._build_splash_screen()
        self._build_home_screen()
        self._build_race_screen()
        self.show_splash()

    def _configure_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("TFrame", background=self.COLORS["bg"])
        style.configure("Card.TFrame", background=self.COLORS["surface"])
        style.configure(
            "Title.TLabel",
            background=self.COLORS["bg"],
            foreground=self.COLORS["accent"],
            font=("Consolas", 24, "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background=self.COLORS["bg"],
            foreground=self.COLORS["muted"],
            font=("Consolas", 11),
        )
        style.configure(
            "PanelTitle.TLabel",
            background=self.COLORS["surface"],
            foreground=self.COLORS["accent"],
            font=("Consolas", 14, "bold"),
        )
        style.configure(
            "TLabel",
            background=self.COLORS["bg"],
            foreground=self.COLORS["text"],
            font=("Consolas", 10),
        )
        style.configure(
            "Green.TButton",
            font=("Consolas", 10, "bold"),
            padding=9,
            background=self.COLORS["button_bg"],
            foreground=self.COLORS["text"],
            bordercolor=self.COLORS["border"],
            lightcolor=self.COLORS["button_bg"],
            darkcolor=self.COLORS["button_bg"],
            relief="solid",
        )
        style.map(
            "Green.TButton",
            background=[("active", self.COLORS["button_active"]), ("pressed", self.COLORS["surface3"])],
            foreground=[("active", self.COLORS["accent"]), ("pressed", self.COLORS["accent"])],
            bordercolor=[("active", self.COLORS["accent"]), ("pressed", self.COLORS["accent2"])],
        )
        style.configure(
            "Start.TButton",
            font=("Consolas", 14, "bold"),
            padding=(26, 14),
            background=self.COLORS["button_bg"],
            foreground=self.COLORS["accent"],
            bordercolor=self.COLORS["accent"],
            lightcolor=self.COLORS["button_bg"],
            darkcolor=self.COLORS["button_bg"],
            relief="solid",
        )
        style.map(
            "Start.TButton",
            background=[("active", self.COLORS["button_active"]), ("pressed", self.COLORS["surface3"])],
            foreground=[("active", self.COLORS["winner"]), ("pressed", self.COLORS["winner"])],
            bordercolor=[("active", self.COLORS["winner"]), ("pressed", self.COLORS["accent2"])],
        )
        style.configure(
            "Cyber.TCombobox",
            fieldbackground=self.COLORS["surface2"],
            background=self.COLORS["surface2"],
            foreground=self.COLORS["text"],
            arrowcolor=self.COLORS["accent"],
            bordercolor=self.COLORS["border"],
            padding=6,
        )
        style.map(
            "Cyber.TCombobox",
            fieldbackground=[("readonly", self.COLORS["surface2"])],
            selectbackground=[("readonly", self.COLORS["surface3"])],
            selectforeground=[("readonly", self.COLORS["accent"])],
        )

    def _load_logo_image(self) -> Optional[tk.PhotoImage]:
        candidates = [
            Path(__file__).with_name("sorting_olympics_logo_transparent.png"),
            Path(__file__).with_name("ChatGPT Image Apr 9, 2026, 12_22_40 PM.png"),
            Path.cwd() / "sorting_olympics_logo_transparent.png",
            Path.cwd() / "ChatGPT Image Apr 9, 2026, 12_22_40 PM.png",
            Path("/mnt/data/sorting_olympics_logo_transparent.png"),
            Path("/mnt/data/ChatGPT Image Apr 9, 2026, 12_22_40 PM.png"),
        ]

        for path in candidates:
            if not path.exists():
                continue
            try:
                photo = tk.PhotoImage(file=str(path))
                if photo.width() > 520:
                    factor = max(1, round(photo.width() / 420))
                    photo = photo.subsample(factor, factor)
                return photo
            except Exception:
                continue
        return None

    def _build_splash_screen(self) -> None:
        self.splash_frame = ttk.Frame(self.root)

        body = ttk.Frame(self.splash_frame)
        body.place(relx=0.5, rely=0.5, anchor="center")

        self.logo_image = self._load_logo_image()
        if self.logo_image is not None:
            logo_label = tk.Label(
                body,
                image=self.logo_image,
                bg=self.COLORS["bg"],
                bd=0,
                highlightthickness=0,
            )
            logo_label.pack(anchor="center", pady=(0, 24))
        else:
            tk.Label(
                body,
                text="SORTING OLYMPICS",
                bg=self.COLORS["bg"],
                fg=self.COLORS["accent"],
                font=("Consolas", 30, "bold"),
                padx=12,
                pady=12,
            ).pack(anchor="center", pady=(0, 24))

        ttk.Button(
            body,
            text="START",
            command=self.show_home,
            style="Start.TButton",
        ).pack(anchor="center")

        tk.Label(
            body,
            text="PRESS START TO ENTER THE ARENA",
            bg=self.COLORS["bg"],
            fg=self.COLORS["muted"],
            font=("Consolas", 10),
            pady=16,
        ).pack(anchor="center")

        tk.Label(
            self.splash_frame,
            text="made by Panagiotis and Barbuchi  (with some help of AI)",
            bg=self.COLORS["bg"],
            fg=self.COLORS["muted"],
            font=("Consolas", 11),
            bd=0,
            highlightthickness=0,
        ).place(relx=0.5, rely=0.92, anchor="center")

    def _build_home_screen(self) -> None:
        self.home_frame = ttk.Frame(self.root)

        outer = ttk.Frame(self.home_frame)
        outer.pack(fill="both", expand=True, padx=34, pady=28)

        top_bar = ttk.Frame(outer)
        top_bar.pack(fill="x", pady=(0, 10))
        ttk.Button(top_bar, text="BACK", command=self.show_splash, style="Green.TButton").pack(side="left")

        home_logo = self.logo_image
        if home_logo is not None and home_logo.width() > 300:
            factor = max(1, round(home_logo.width() / 280))
            self.home_logo_image = home_logo.subsample(factor, factor)
            home_logo = self.home_logo_image
        else:
            self.home_logo_image = home_logo

        if home_logo is not None:
            tk.Label(
                outer,
                image=home_logo,
                bg=self.COLORS["bg"],
                bd=0,
                highlightthickness=0,
            ).pack(anchor="center", pady=(0, 6))
        else:
            ttk.Label(outer, text="SORTING OLYMPICS", style="Title.TLabel").pack(anchor="center")

        ttk.Label(
            outer,
            text="PICK A 1v1 MATCHUP OR RUN THE FULL 6-ALGORITHM SHOWDOWN",
            style="Subtitle.TLabel",
        ).pack(anchor="center", pady=(4, 20))

        card = ttk.Frame(outer, style="Card.TFrame")
        card.pack(fill="both", expand=True)

        hero = tk.Label(
            card,
            text=(
                "> Select the algorithms you want on the track.\n"
                "> Every racer gets the exact same shuffled dataset.\n"
                "> Launch a 1v1 duel or compare all six at once."
            ),
            justify="left",
            bg=self.COLORS["surface"],
            fg=self.COLORS["accent2"],
            font=("Consolas", 14),
            padx=18,
            pady=18,
        )
        hero.pack(fill="x", padx=18, pady=(18, 8))

        config_row = ttk.Frame(card, style="Card.TFrame")
        config_row.pack(fill="x", padx=18, pady=(8, 10))

        left = ttk.Frame(config_row, style="Card.TFrame")
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        ttk.Label(left, text="1v1 SELECTION", style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 10))

        pick_row = ttk.Frame(left, style="Card.TFrame")
        pick_row.pack(anchor="w", pady=(0, 12))

        ttk.Label(pick_row, text="ALGO A").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.algo1_box = ttk.Combobox(
            pick_row,
            values=list(self.algorithms.keys()),
            textvariable=self.algo1_var,
            state="readonly",
            width=18,
            style="Cyber.TCombobox",
        )
        self.algo1_box.grid(row=0, column=1, padx=(0, 18), pady=4)

        ttk.Label(pick_row, text="ALGO B").grid(row=0, column=2, sticky="w", padx=(0, 8), pady=4)
        self.algo2_box = ttk.Combobox(
            pick_row,
            values=list(self.algorithms.keys()),
            textvariable=self.algo2_var,
            state="readonly",
            width=18,
            style="Cyber.TCombobox",
        )
        self.algo2_box.grid(row=0, column=3, padx=(0, 8), pady=4)

        action_row = ttk.Frame(left, style="Card.TFrame")
        action_row.pack(anchor="w", pady=(4, 0))
        ttk.Button(action_row, text="START 1v1", command=self.start_1v1, style="Green.TButton").pack(side="left", padx=(0, 10))
        ttk.Button(action_row, text="COMPARE ALL 6", command=self.start_all, style="Green.TButton").pack(side="left")

        right = ttk.Frame(config_row, style="Card.TFrame")
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))

        ttk.Label(right, text="MATCH SETTINGS", style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 10))

        size_row = ttk.Frame(right, style="Card.TFrame")
        size_row.pack(fill="x", pady=(0, 6))
        ttk.Label(size_row, text="ARRAY SIZE").pack(side="left")
        self.home_size_scale = tk.Scale(
            size_row,
            from_=12,
            to=90,
            orient="horizontal",
            variable=self.size_var,
            bg=self.COLORS["surface"],
            fg=self.COLORS["accent"],
            activebackground=self.COLORS["surface3"],
            troughcolor=self.COLORS["surface2"],
            highlightthickness=0,
            length=220,
        )
        self.home_size_scale.pack(side="left", padx=(12, 0))

        speed_row = ttk.Frame(right, style="Card.TFrame")
        speed_row.pack(fill="x", pady=(0, 6))
        ttk.Label(speed_row, text="TICK SPEED").pack(side="left")
        self.home_speed_scale = tk.Scale(
            speed_row,
            from_=1,
            to=30,
            orient="horizontal",
            variable=self.speed_var,
            bg=self.COLORS["surface"],
            fg=self.COLORS["accent"],
            activebackground=self.COLORS["surface3"],
            troughcolor=self.COLORS["surface2"],
            highlightthickness=0,
            length=220,
        )
        self.home_speed_scale.pack(side="left", padx=(12, 0))

        sound_row = ttk.Frame(right, style="Card.TFrame")
        sound_row.pack(fill="x")
        tk.Checkbutton(
            sound_row,
            text="8-bit sound",
            variable=self.sound_var,
            command=self.on_sound_toggle,
            bg=self.COLORS["surface"],
            fg=self.COLORS["text"],
            activebackground=self.COLORS["surface"],
            activeforeground=self.COLORS["accent"],
            selectcolor=self.COLORS["surface2"],
            highlightthickness=0,
            font=("Consolas", 10),
        ).pack(side="left")

        info_panel = ttk.Frame(card, style="Card.TFrame")
        info_panel.pack(fill="both", expand=True, padx=18, pady=12)

        ttk.Label(info_panel, text="AVAILABLE ALGORITHMS", style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 10))

        info_grid = ttk.Frame(info_panel, style="Card.TFrame")
        info_grid.pack(fill="both", expand=True)
        for c in range(3):
            info_grid.columnconfigure(c, weight=1, uniform="info")

        for idx, (name, meta) in enumerate(self.algorithms.items()):
            panel = tk.Frame(
                info_grid,
                bg=self.COLORS["surface2"],
                highlightthickness=1,
                highlightbackground=self.COLORS["border"],
                padx=12,
                pady=10,
            )
            r, c = divmod(idx, 3)
            panel.grid(row=r, column=c, sticky="nsew", padx=6, pady=6)
            tk.Label(panel, text=name, bg=self.COLORS["surface2"], fg=self.COLORS["accent"], font=("Consolas", 12, "bold")).pack(anchor="w")
            tk.Label(
                panel,
                text=meta["desc"],
                bg=self.COLORS["surface2"],
                fg=self.COLORS["muted"],
                font=("Consolas", 10),
                wraplength=320,
                justify="left",
            ).pack(anchor="w", pady=(4, 0))

        status = tk.Label(
            card,
            textvariable=self.home_status_var,
            bg=self.COLORS["surface"],
            fg=self.COLORS["accent"],
            font=("Consolas", 11, "bold"),
            anchor="w",
            padx=18,
            pady=12,
        )
        status.pack(fill="x", padx=18, pady=(0, 18))

    def _build_race_screen(self) -> None:
        self.race_frame = ttk.Frame(self.root)

        outer = ttk.Frame(self.race_frame)
        outer.pack(fill="both", expand=True, padx=18, pady=16)

        self.race_title_var = tk.StringVar(value="MATCH // READY")
        ttk.Label(outer, textvariable=self.race_title_var, style="Title.TLabel").pack(anchor="center")
        self.race_subtitle_var = tk.StringVar(value="")
        ttk.Label(outer, textvariable=self.race_subtitle_var, style="Subtitle.TLabel").pack(anchor="center", pady=(4, 12))

        top_controls = ttk.Frame(outer)
        top_controls.pack(fill="x", pady=(0, 12))

        self.start_abort_btn = ttk.Button(top_controls, text="START RACE", command=self.toggle_race, style="Green.TButton")
        self.start_abort_btn.pack(side="left", padx=(0, 8))

        ttk.Button(top_controls, text="RESHUFFLE", command=self.reshuffle_only, style="Green.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(top_controls, text="RESTART SAME MATCH", command=self.restart_same_match, style="Green.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(top_controls, text="HOME", command=self.show_home, style="Green.TButton").pack(side="left", padx=(0, 16))

        ttk.Label(top_controls, text="SIZE").pack(side="left")
        self.race_size_scale = tk.Scale(
            top_controls,
            from_=12,
            to=90,
            orient="horizontal",
            variable=self.size_var,
            command=lambda _=None: self.on_race_size_change(),
            bg=self.COLORS["bg"],
            fg=self.COLORS["accent"],
            activebackground=self.COLORS["surface3"],
            troughcolor=self.COLORS["surface2"],
            highlightthickness=0,
            length=120,
        )
        self.race_size_scale.pack(side="left", padx=(6, 14))

        ttk.Label(top_controls, text="SPEED").pack(side="left")
        self.race_speed_scale = tk.Scale(
            top_controls,
            from_=1,
            to=30,
            orient="horizontal",
            variable=self.speed_var,
            bg=self.COLORS["bg"],
            fg=self.COLORS["accent"],
            activebackground=self.COLORS["surface3"],
            troughcolor=self.COLORS["surface2"],
            highlightthickness=0,
            length=120,
        )
        self.race_speed_scale.pack(side="left", padx=(6, 14))

        tk.Checkbutton(
            top_controls,
            text="8-bit sound",
            variable=self.sound_var,
            command=self.on_sound_toggle,
            bg=self.COLORS["bg"],
            fg=self.COLORS["text"],
            activebackground=self.COLORS["bg"],
            activeforeground=self.COLORS["accent"],
            selectcolor=self.COLORS["surface2"],
            highlightthickness=0,
            font=("Consolas", 10),
        ).pack(side="left", padx=(0, 16))

        ttk.Label(top_controls, textvariable=self.winner_var, style="Subtitle.TLabel").pack(side="right")

        self.race_grid = ttk.Frame(outer)
        self.race_grid.pack(fill="both", expand=True)

        self.results_bar = tk.Label(
            outer,
            textvariable=self.results_var,
            bg=self.COLORS["surface"],
            fg=self.COLORS["accent2"],
            font=("Consolas", 10, "bold"),
            justify="left",
            anchor="w",
            padx=16,
            pady=12,
        )
        self.results_bar.pack(fill="x", pady=(12, 0))

    def on_sound_toggle(self) -> None:
        self.sound.set_enabled(self.sound_var.get())
        if not self.sound_var.get():
            self.sound.clear()

    def show_splash(self) -> None:
        self.stop_race(set_status=False)
        self.home_frame.pack_forget()
        self.race_frame.pack_forget()
        self.splash_frame.pack(fill="both", expand=True)

    def show_home(self) -> None:
        self.stop_race(set_status=False)
        self.splash_frame.pack_forget()
        self.race_frame.pack_forget()
        self.home_frame.pack(fill="both", expand=True)
        self.home_status_var.set("> SELECT TWO ALGORITHMS FOR A 1v1, OR RUN THE FULL 6-ALGORITHM EVENT.")

    def show_race(self) -> None:
        self.splash_frame.pack_forget()
        self.home_frame.pack_forget()
        self.race_frame.pack(fill="both", expand=True)

    def start_1v1(self) -> None:
        a = self.algo1_var.get()
        b = self.algo2_var.get()
        if a == b:
            self.home_status_var.set("> ERROR: PICK TWO DIFFERENT ALGORITHMS FOR THE 1v1.")
            return
        self.setup_match([a, b], "1v1 DUEL")

    def start_all(self) -> None:
        self.setup_match(list(self.algorithms.keys()), "FULL 6-ALGORITHM SHOWDOWN")

    def setup_match(self, names: List[str], mode_label: str) -> None:
        self.stop_race(set_status=False)
        self.current_mode = mode_label
        self.current_algorithms = names[:]
        self.racers = []
        self.finished_count = 0
        self.winner_var.set("WINNER: ---")
        self.results_var.set("RESULTS: match loaded. press START RACE, or use RESTART SAME MATCH for instant replay.")
        self.race_title_var.set(f"MATCH // {mode_label}")
        self.race_subtitle_var.set(" // ".join(names))

        for widget in self.race_grid.winfo_children():
            widget.destroy()

        cols = 2 if len(names) <= 2 else 3
        rows = (len(names) + cols - 1) // cols
        for c in range(cols):
            self.race_grid.columnconfigure(c, weight=1, uniform="race")
        for r in range(rows):
            self.race_grid.rowconfigure(r, weight=1)

        for idx, name in enumerate(names):
            meta = self.algorithms[name]
            racer = Racer(name, meta["desc"], meta["fn"])
            self.racers.append(racer)
            self._build_racer_panel(racer, idx, cols)

        self.create_shared_array()
        self.show_race()
        self.root.after(120, self.start_race)

    def _build_racer_panel(self, racer: Racer, idx: int, cols: int) -> None:
        panel = ttk.Frame(self.race_grid, style="Card.TFrame")
        row, col = divmod(idx, cols)
        panel.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)

        ttk.Label(panel, text=racer.name, style="PanelTitle.TLabel").pack(anchor="w", padx=12, pady=(10, 2))
        desc = tk.Label(
            panel,
            text=racer.description,
            bg=self.COLORS["surface"],
            fg=self.COLORS["muted"],
            justify="left",
            wraplength=430 if cols == 2 else 290,
            font=("Consolas", 9),
        )
        desc.pack(fill="x", padx=12, pady=(0, 8))

        racer.canvas = tk.Canvas(
            panel,
            height=300 if cols == 2 else 245,
            bg=self.COLORS["surface2"],
            highlightthickness=1,
            highlightbackground=self.COLORS["border"],
        )
        racer.canvas.pack(fill="both", expand=True, padx=12)

        stats = ttk.Frame(panel, style="Card.TFrame")
        stats.pack(fill="x", padx=12, pady=10)

        racer.cmp_var = tk.StringVar(value="COMPARISONS: 0")
        racer.swap_var = tk.StringVar(value="WRITES: 0")
        racer.time_var = tk.StringVar(value="TIME: 0 ms")
        racer.status_var = tk.StringVar(value="STATUS: standby")

        for var in (racer.cmp_var, racer.swap_var, racer.time_var, racer.status_var):
            lbl = tk.Label(
                stats,
                textvariable=var,
                bg=self.COLORS["surface"],
                fg=self.COLORS["text"],
                anchor="w",
                font=("Consolas", 9),
            )
            lbl.pack(fill="x")

    def create_shared_array(self) -> None:
        n = self.size_var.get()
        base = [max(5, round((i + 1) / n * 280)) for i in range(n)]
        random.shuffle(base)

        for racer in self.racers:
            racer.array = base.copy()
            self.reset_racer_stats(racer)
            self.draw_racer(racer)

    def reset_racer_stats(self, racer: Racer) -> None:
        racer.comparisons = 0
        racer.swaps = 0
        racer.finished = False
        racer.finish_time_ms = None
        racer.rank = None
        racer.generator = None
        if racer.cmp_var:
            racer.cmp_var.set("COMPARISONS: 0")
        if racer.swap_var:
            racer.swap_var.set("WRITES: 0")
        if racer.time_var:
            racer.time_var.set("TIME: 0 ms")
        if racer.status_var:
            racer.status_var.set("STATUS: standby")

    def on_race_size_change(self) -> None:
        if not self.running and self.racers:
            self.create_shared_array()
            self.results_var.set("RESULTS: dataset regenerated with the new size.")

    def reshuffle_only(self) -> None:
        self.stop_race(set_status=False)
        if self.racers:
            self.create_shared_array()
            self.winner_var.set("WINNER: ---")
            self.results_var.set("RESULTS: reshuffled. press START RACE to run again.")
            self.start_abort_btn.config(text="START RACE")

    def restart_same_match(self) -> None:
        self.stop_race(set_status=False)
        if self.racers:
            self.create_shared_array()
            self.start_race()

    def toggle_race(self) -> None:
        if self.running:
            self.stop_race(set_status=True)
        else:
            self.start_race()

    def get_delay(self) -> int:
        return max(1, 34 - self.speed_var.get())

    def start_race(self) -> None:
        if not self.racers:
            return
        self.running = True
        self.finished_count = 0
        self.start_time = time.perf_counter()
        self.winner_var.set("WINNER: ---")
        self.results_var.set("RESULTS: race in progress... live placements will appear as algorithms finish.")
        self.start_abort_btn.config(text="ABORT")
        self.sound.clear()

        for racer in self.racers:
            self.reset_racer_stats(racer)
            if racer.status_var:
                racer.status_var.set("STATUS: running")
            racer.generator = racer.algorithm(racer)
            self.draw_racer(racer)

        self.step_all()

    def stop_race(self, set_status: bool = True) -> None:
        self.running = False
        self.sound.clear()
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self.start_abort_btn.config(text="START RACE")
        if set_status:
            for racer in self.racers:
                if not racer.finished and racer.status_var:
                    racer.status_var.set("STATUS: halted")
            if self.racers:
                self.results_var.set("RESULTS: race aborted. reshuffle, restart, or go back home.")

    def step_all(self) -> None:
        if not self.running:
            return

        for racer in self.racers:
            if racer.finished or racer.generator is None:
                continue
            try:
                event = next(racer.generator)
                highlights = event.get("highlights", {})
                self.draw_racer(racer, highlights if isinstance(highlights, dict) else {})
                elapsed = int((time.perf_counter() - self.start_time) * 1000)
                if racer.time_var:
                    racer.time_var.set(f"TIME: {elapsed} ms")

                sound_pair = event.get("sound")
                if (
                    self.sound_var.get()
                    and isinstance(sound_pair, tuple)
                    and len(sound_pair) == 2
                    and racer.array
                ):
                    self.sound.play_compare(
                        float(sound_pair[0]),
                        float(sound_pair[1]),
                        max(racer.array),
                        self.speed_var.get(),
                    )
            except StopIteration:
                self.mark_finished(racer)

        if self.finished_count == len(self.racers):
            self.running = False
            self.start_abort_btn.config(text="START RACE")
            self.update_results_summary(final=True)
            return

        self.after_id = self.root.after(self.get_delay(), self.step_all)

    def mark_finished(self, racer: Racer) -> None:
        racer.finished = True
        self.finished_count += 1
        racer.rank = self.finished_count
        racer.finish_time_ms = int((time.perf_counter() - self.start_time) * 1000)
        if racer.time_var:
            racer.time_var.set(f"TIME: {racer.finish_time_ms} ms")

        if racer.rank == 1:
            if racer.status_var:
                racer.status_var.set("STATUS: WINNER // ACCESS GRANTED")
            self.winner_var.set(f"WINNER: {racer.name} // {racer.finish_time_ms} ms")
        else:
            if racer.status_var:
                racer.status_var.set(f"STATUS: finished #{racer.rank}")

        fill = "winner" if racer.rank == 1 else "sorted"
        self.draw_racer(racer, {i: fill for i in range(len(racer.array))})

        if racer.array and self.sound_var.get():
            self.sound.play_finish(max(racer.array))

        self.update_results_summary(final=False)

    def update_results_summary(self, final: bool) -> None:
        finished = [r for r in self.racers if r.finished]
        finished.sort(key=lambda r: (r.rank or 999, r.finish_time_ms or 10**9))
        if not finished:
            return

        placements = []
        medals = {1: "1ST", 2: "2ND", 3: "3RD"}
        for racer in finished:
            tag = medals.get(racer.rank, f"{racer.rank}TH")
            placements.append(f"{tag}: {racer.name} ({racer.finish_time_ms} ms)")

        if final:
            self.results_var.set("RESULTS: " + "  //  ".join(placements) + "  //  USE RESTART SAME MATCH TO RUN IT AGAIN.")
        else:
            self.results_var.set("RESULTS: " + "  //  ".join(placements))

    def draw_racer(self, racer: Racer, highlights: Optional[Highlight] = None) -> None:
        if racer.canvas is None:
            return
        if highlights is None:
            highlights = {}

        canvas = racer.canvas
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        n = len(racer.array)
        if n == 0:
            return

        gap = 1
        bar_width = max(2, (width - (n + 1) * gap) / n)
        max_value = max(racer.array) if racer.array else 1

        for i, value in enumerate(racer.array):
            x0 = gap + i * (bar_width + gap)
            x1 = x0 + bar_width
            y1 = height - 8
            scaled = (value / max_value) * (height - 18)
            y0 = y1 - scaled
            state = highlights.get(i, "default")
            color = self.COLORS.get(state, self.COLORS["default"])
            canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")

    def refresh_stats(self, racer: Racer) -> None:
        if racer.cmp_var:
            racer.cmp_var.set(f"COMPARISONS: {racer.comparisons}")
        if racer.swap_var:
            racer.swap_var.set(f"WRITES: {racer.swaps}")

    # ---------------- Sorting algorithms ----------------

    def bubble_sort_steps(self, racer: Racer) -> StepGenerator:
        arr = racer.array
        n = len(arr)
        for i in range(n):
            for j in range(0, n - i - 1):
                racer.comparisons += 1
                self.refresh_stats(racer)
                yield {"highlights": {j: "compare", j + 1: "compare"}, "sound": (arr[j], arr[j + 1])}
                if arr[j] > arr[j + 1]:
                    arr[j], arr[j + 1] = arr[j + 1], arr[j]
                    racer.swaps += 1
                    self.refresh_stats(racer)
                    yield {"highlights": {j: "swap", j + 1: "swap"}}

    def selection_sort_steps(self, racer: Racer) -> StepGenerator:
        arr = racer.array
        n = len(arr)
        for i in range(n):
            min_i = i
            for j in range(i + 1, n):
                racer.comparisons += 1
                self.refresh_stats(racer)
                yield {"highlights": {min_i: "pivot", j: "compare"}, "sound": (arr[min_i], arr[j])}
                if arr[j] < arr[min_i]:
                    min_i = j
                    yield {"highlights": {min_i: "pivot"}}
            if min_i != i:
                arr[i], arr[min_i] = arr[min_i], arr[i]
                racer.swaps += 1
                self.refresh_stats(racer)
                yield {"highlights": {i: "swap", min_i: "swap"}}

    def insertion_sort_steps(self, racer: Racer) -> StepGenerator:
        arr = racer.array
        for i in range(1, len(arr)):
            j = i
            while j > 0:
                racer.comparisons += 1
                self.refresh_stats(racer)
                yield {"highlights": {j: "compare", j - 1: "compare"}, "sound": (arr[j], arr[j - 1])}
                if arr[j] < arr[j - 1]:
                    arr[j], arr[j - 1] = arr[j - 1], arr[j]
                    racer.swaps += 1
                    self.refresh_stats(racer)
                    yield {"highlights": {j: "swap", j - 1: "swap"}}
                    j -= 1
                else:
                    break

    def merge_sort_steps(self, racer: Racer) -> StepGenerator:
        arr = racer.array

        def merge_sort(lo: int, hi: int) -> StepGenerator:
            if lo >= hi:
                return
            mid = (lo + hi) // 2
            yield from merge_sort(lo, mid)
            yield from merge_sort(mid + 1, hi)

            left = arr[lo:mid + 1]
            right = arr[mid + 1:hi + 1]
            i = j = 0
            k = lo

            while i < len(left) and j < len(right):
                racer.comparisons += 1
                self.refresh_stats(racer)
                yield {"highlights": {k: "compare", lo + i: "pivot", mid + 1 + j: "pivot"}, "sound": (left[i], right[j])}
                if left[i] <= right[j]:
                    arr[k] = left[i]
                    i += 1
                else:
                    arr[k] = right[j]
                    j += 1
                racer.swaps += 1
                self.refresh_stats(racer)
                yield {"highlights": {k: "swap"}}
                k += 1

            while i < len(left):
                arr[k] = left[i]
                i += 1
                racer.swaps += 1
                self.refresh_stats(racer)
                yield {"highlights": {k: "swap"}}
                k += 1

            while j < len(right):
                arr[k] = right[j]
                j += 1
                racer.swaps += 1
                self.refresh_stats(racer)
                yield {"highlights": {k: "swap"}}
                k += 1

        yield from merge_sort(0, len(arr) - 1)

    def quick_sort_steps(self, racer: Racer) -> StepGenerator:
        arr = racer.array

        def quick_sort(lo: int, hi: int) -> StepGenerator:
            if lo >= hi:
                return

            pivot = arr[hi]
            i = lo
            for j in range(lo, hi):
                racer.comparisons += 1
                self.refresh_stats(racer)
                yield {"highlights": {j: "compare", hi: "pivot", i: "swap"}, "sound": (arr[j], pivot)}
                if arr[j] < pivot:
                    arr[i], arr[j] = arr[j], arr[i]
                    racer.swaps += 1
                    self.refresh_stats(racer)
                    yield {"highlights": {i: "swap", j: "swap"}}
                    i += 1

            arr[i], arr[hi] = arr[hi], arr[i]
            racer.swaps += 1
            self.refresh_stats(racer)
            yield {"highlights": {i: "pivot", hi: "swap"}}

            yield from quick_sort(lo, i - 1)
            yield from quick_sort(i + 1, hi)

        yield from quick_sort(0, len(arr) - 1)

    def heap_sort_steps(self, racer: Racer) -> StepGenerator:
        arr = racer.array
        n = len(arr)

        def heapify(size: int, i: int) -> StepGenerator:
            largest = i
            left = 2 * i + 1
            right = 2 * i + 2

            if left < size:
                racer.comparisons += 1
                self.refresh_stats(racer)
                yield {"highlights": {i: "pivot", left: "compare"}, "sound": (arr[largest], arr[left])}
                if arr[left] > arr[largest]:
                    largest = left

            if right < size:
                racer.comparisons += 1
                self.refresh_stats(racer)
                yield {"highlights": {largest: "pivot", right: "compare"}, "sound": (arr[largest], arr[right])}
                if arr[right] > arr[largest]:
                    largest = right

            if largest != i:
                arr[i], arr[largest] = arr[largest], arr[i]
                racer.swaps += 1
                self.refresh_stats(racer)
                yield {"highlights": {i: "swap", largest: "swap"}}
                yield from heapify(size, largest)

        for i in range(n // 2 - 1, -1, -1):
            yield from heapify(n, i)

        for end in range(n - 1, 0, -1):
            arr[0], arr[end] = arr[end], arr[0]
            racer.swaps += 1
            self.refresh_stats(racer)
            yield {"highlights": {0: "swap", end: "sorted"}}
            yield from heapify(end, 0)


if __name__ == "__main__":
    root = tk.Tk()
    app = SortingTournamentApp(root)
    root.mainloop()
