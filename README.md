# Sorting-Algorithms-Project
Interactive Python sorting algorithm visualizer with real-time bar animations and 8-bit sound feedback. Supports multiple algorithms, adjustable speed and array size, and displays comparisons, swaps, and execution time using a Tkinter GUI.
Features
📊 Real-time sorting visualization
🔊 Optional 8-bit sound feedback
⚡ Adjustable sorting speed
🎚 Adjustable array size
🔀 Shuffle array instantly
📈 Live statistics:
Comparisons
Swaps
Execution time
🎨 Modern Tkinter GUI
🔔 Automatic sound fallback if audio library is unavailable
🧠 Algorithms Included

The visualizer currently supports:

Bubble Sort
Selection Sort
Insertion Sort
Merge Sort
Quick Sort
Heap Sort
Comb Sort

Each algorithm runs step-by-step so the visualization can animate each comparison and swap.

🔊 Sound System

The application includes a custom SoundEngine that generates tones based on the values being compared.

Each comparison produces a short tone.
Tone pitch changes depending on the element values.
When sorting finishes, a short ascending melody plays.

If the simpleaudio library is installed, real audio will be played.
Otherwise, the program falls back to the system Tkinter bell sound.

📦 Installation
1. Clone the repository
git clone https://github.com/yourusername/sorting-visualizer-sound.git
cd sorting-visualizer-sound
2. Install optional dependency for sound
pip install simpleaudio
3. Run the program
python sorting_visualizer.py
🎮 How to Use
Choose a sorting algorithm from the dropdown menu.
Adjust the array size and sorting speed.
Click Shuffle to generate a random array.
Click Sort to start the visualization.
Enable or disable 8-bit sound using the toggle.

Watch the bars move and listen to the sorting process in real time.

🛠 Built With
Python
Tkinter – GUI framework
simpleaudio – sound playback
threading & queues – asynchronous sound handling
🎓 Educational Purpose

This project helps students and developers:

Understand how sorting algorithms operate internally
Compare different algorithms visually
Experience algorithm behavior through visual + audio feedback
🚀 Possible Future Improvements
More algorithms (Shell Sort, Radix Sort)
Pause / step mode
Dark/light themes
Algorithm complexity display
Export visualization as GIF or video

⭐ If you find this project useful, consider starring the repository!
