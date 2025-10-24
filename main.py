

import time
import sys
from pynput.mouse import Controller, Button
from pynput import mouse

import nltk
try:
    from nltk.corpus import words
    nltk.data.find('corpora/words')
    WORD_LIST = set(w.upper() for w in words.words() if len(w) >= 3)
    print(f"✓ Loaded {len(WORD_LIST)} words from NLTK")
except LookupError:
    print("Downloading NLTK words corpus...")
    nltk.download('words', quiet=True)
    from nltk.corpus import words
    WORD_LIST = set(w.upper() for w in words.words() if len(w) >= 3)
    print(f"✓ Loaded {len(WORD_LIST)} words from NLTK")

# Initialize mouse controller
mouse_controller = Controller()

# ============= CONFIGURATION =============


class Config:
    """Configuration for timing and behavior settings"""

    # Timing settings (in seconds)
    MOVE_TO_CELL_DELAY = 0.02        # Delay after moving to a cell
    PRESS_DOWN_DELAY = 0.02          # Delay after pressing mouse button
    BETWEEN_CELLS_DELAY = 0.01       # Delay between moving to each cell
    BEFORE_RELEASE_DELAY = 0.02      # Delay before releasing mouse button
    BETWEEN_WORDS_DELAY = 0.05       # Delay between playing different words
    SMOOTH_MOVE_DURATION = 0.03      # Duration for smooth movement between cells
    STARTUP_DELAY = 3                # Countdown before starting automation

    # Behavior settings
    MIN_WORD_LENGTH = 3              # Minimum word length to find
    SORT_BY_LENGTH = True            # Sort words by length (longest first)
    FOCUS_CLICK_ENABLED = True       # Click to focus window before playing

    # Display settings
    SHOW_TOP_N_WORDS = 50            # Number of top words to display initially

# =========================================


class TrieNode:
    """Trie structure for efficient word lookup"""

    def __init__(self):
        self.children = {}
        self.is_word = False
        self.word = None


class Trie:
    """Trie for dictionary lookups"""

    def __init__(self):
        self.root = TrieNode()

    def insert(self, word):
        node = self.root
        for char in word:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
        node.is_word = True
        node.word = word


def build_trie():
    """Build trie from word list"""
    trie = Trie()
    for word in WORD_LIST:
        trie.insert(word)
    return trie


def capture_board_region():
    """Capture the game board region"""
    print("\n=== BOARD CAPTURE ===")
    print("Move your mouse to the CENTER of the TOP-LEFT cell and press Enter...")
    input()

    x1, y1 = mouse_controller.position
    print(f"Top-left cell center: ({x1}, {y1})")

    print("Move your mouse to the CENTER of the BOTTOM-RIGHT cell and press Enter...")
    input()

    x2, y2 = mouse_controller.position
    print(f"Bottom-right cell center: ({x2}, {y2})")

    return None, (x1, y1, x2-x1, y2-y1)


def extract_board_manual():
    """Manually input board"""
    print("\n=== MANUAL BOARD INPUT ===")
    print("Enter the 4x4 board letters row by row (e.g., ABCD)")
    board = []
    for i in range(4):
        while True:
            row = input(f"Row {i+1}: ").strip().upper()
            if len(row) == 4 and row.isalpha():
                board.append(list(row))
                break
            print("Please enter exactly 4 letters")
    return board


def print_board(board):
    """Print the board nicely"""
    print("\n" + "="*17)
    for row in board:
        print("| " + " | ".join(row) + " |")
        print("="*17)


def find_words(board, trie):
    """Find all valid words in the board using DFS"""
    words_found = []
    rows, cols = len(board), len(board[0])

    def dfs(row, col, path, visited, node):
        if node.is_word and len(node.word) >= Config.MIN_WORD_LENGTH:
            words_found.append((node.word, list(path)))

        # Explore all 8 directions
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue

                nr, nc = row + dr, col + dc

                if (0 <= nr < rows and 0 <= nc < cols and
                        (nr, nc) not in visited):

                    letter = board[nr][nc]
                    if letter in node.children:
                        visited.add((nr, nc))
                        path.append((nr, nc))
                        dfs(nr, nc, path, visited, node.children[letter])
                        path.pop()
                        visited.remove((nr, nc))

    # Try starting from each cell
    for i in range(rows):
        for j in range(cols):
            letter = board[i][j]
            if letter in trie.root.children:
                visited = {(i, j)}
                path = [(i, j)]
                dfs(i, j, path, visited, trie.root.children[letter])

    # Remove duplicates
    unique_words = {}
    for word, path in words_found:
        if word not in unique_words:
            unique_words[word] = path

    # Sort based on config
    if Config.SORT_BY_LENGTH:
        return sorted(unique_words.items(), key=lambda x: len(x[0]), reverse=True)
    else:
        return sorted(unique_words.items(), key=lambda x: x[0])


def calculate_cell_positions(region):
    """Calculate center positions of each cell"""
    x, y, width, height = region

    # For a 4x4 grid where we marked the centers of corner cells
    cell_width = width / 3
    cell_height = height / 3

    positions = []
    for row in range(4):
        row_positions = []
        for col in range(4):
            cx = x + (col * cell_width)
            cy = y + (row * cell_height)
            row_positions.append((int(cx), int(cy)))
        positions.append(row_positions)

    return positions


def smooth_move(x, y, duration=None):
    """Smoothly move mouse to position"""
    if duration is None:
        duration = Config.SMOOTH_MOVE_DURATION

    start_x, start_y = mouse_controller.position
    steps = int(duration * 60)  # 60 steps per second

    if steps < 1:
        steps = 1

    for i in range(steps + 1):
        t = i / steps
        # Ease in-out
        t = t * t * (3 - 2 * t)
        current_x = start_x + (x - start_x) * t
        current_y = start_y + (y - start_y) * t
        mouse_controller.position = (current_x, current_y)
        time.sleep(duration / steps)


def play_word_pynput(word, path, positions):
    """Play a word using pynput for hardware-level events"""
    if not path:
        return

    print(f"Playing: {word} ({len(path)} letters)")

    # Get all coordinates
    coords = [positions[r][c] for r, c in path]

    # Move to first position
    x, y = coords[0]
    mouse_controller.position = (x, y)
    time.sleep(Config.MOVE_TO_CELL_DELAY)

    # Press down
    mouse_controller.press(Button.left)
    time.sleep(Config.PRESS_DOWN_DELAY)

    # Move through each position while held
    for i, (x, y) in enumerate(coords[1:], 1):
        # Smooth movement
        smooth_move(x, y)
        time.sleep(Config.BETWEEN_CELLS_DELAY)

    # Small pause before release
    time.sleep(Config.BEFORE_RELEASE_DELAY)

    # Release
    mouse_controller.release(Button.left)
    time.sleep(Config.BETWEEN_WORDS_DELAY)


def main():
    print("="*50)
    print("WORD HUNT SOLVER - pynput Edition")
    print("="*50)
    print("\nUsing pynput for hardware-level mouse events")
    print("This should work better with iPhone Mirroring!")

    # Build trie
    print("\nBuilding trie...")
    trie = build_trie()
    print("✓ Trie built successfully")

    # Capture board
    img, region = capture_board_region()

    # Manual board input
    print("\nEnter the board letters:")
    board = extract_board_manual()
    print_board(board)

    # Find words
    print("\nFinding words...")
    words = find_words(board, trie)

    if not words:
        print("No words found! Check the board input.")
        return

    print(f"\n✓ Found {len(words)} words!")
    print(f"\nTop {Config.SHOW_TOP_N_WORDS} words:")
    for word, path in words[:Config.SHOW_TOP_N_WORDS]:
        print(f"  {word} ({len(word)} letters)")

    # Calculate cell positions
    positions = calculate_cell_positions(region)

    # Ask to play
    print("\n" + "="*50)
    choice = input("\nPlay words automatically? (y/n): ").lower()

    if choice == 'y':
        print(f"\n⚠️  Make sure iPhone Mirroring window is focused!")
        print(f"Starting in {Config.STARTUP_DELAY} seconds...")
        time.sleep(Config.STARTUP_DELAY)

        # Focus click if enabled
        if Config.FOCUS_CLICK_ENABLED:
            print("Clicking to focus window...")
            center_x = region[0] + region[2] // 2
            center_y = region[1] + region[3] // 2
            mouse_controller.position = (center_x, center_y)
            time.sleep(0.1)
            mouse_controller.click(Button.left)
            time.sleep(0.3)

        played = 0
        for word, path in words:
            try:
                play_word_pynput(word, path, positions)
                played += 1
            except KeyboardInterrupt:
                print("\n\nStopped by user")
                break

        print(f"\n✅ Finished! Played {played} words.")
    else:
        print("\nWords listed above. Happy hunting!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nStopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
