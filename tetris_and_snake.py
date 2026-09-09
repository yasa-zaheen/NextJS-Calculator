#!/usr/bin/env python3
"""
Playable Tetris + Snake (single script).

Controls
--------
Start screen:
  1: Tetris
  2: Snake
  ESC: Quit

Tetris:
  Left/Right: Move
  Down: Soft drop (faster)
  Up or X: Rotate
  Space: Hard drop
  P: Pause
  R (after game over): Restart
  ESC (after game over): Back to menu

Snake:
  Arrow keys / WASD: Move
  P: Pause
  R (after game over): Restart
  ESC (after game over): Back to menu
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

try:
    import pygame
except ImportError as e:
    raise SystemExit(
        "pygame is required. Install it with:\n"
        "  pip install pygame\n\n"
        f"Original error: {e}"
    )


Vec2 = Tuple[int, int]


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def rotate_matrix_clockwise(mat: List[List[int]]) -> List[List[int]]:
    # 4x4 (or NxN): rotate clockwise.
    n = len(mat)
    return [[mat[n - 1 - r][c] for r in range(n)] for c in range(n)]


def matrices_equal(a: List[List[int]], b: List[List[int]]) -> bool:
    if len(a) != len(b) or len(a[0]) != len(b[0]):
        return False
    for r in range(len(a)):
        for c in range(len(a[0])):
            if a[r][c] != b[r][c]:
                return False
    return True


def unique_rotations(base: List[List[int]]) -> List[List[List[int]]]:
    rots: List[List[List[int]]] = []
    cur = base
    for _ in range(4):
        if not any(matrices_equal(cur, x) for x in rots):
            rots.append(cur)
        cur = rotate_matrix_clockwise(cur)
    return rots


def matrix_to_blocks(mat: List[List[int]]) -> List[Tuple[int, int]]:
    blocks: List[Tuple[int, int]] = []
    for y in range(len(mat)):
        for x in range(len(mat[y])):
            if mat[y][x]:
                blocks.append((x, y))
    return blocks


COLORS = {
    # tetris colors: index must match the tetris kind map below
    "I": (0, 240, 240),
    "O": (240, 240, 0),
    "T": (180, 0, 240),
    "S": (0, 200, 0),
    "Z": (220, 0, 0),
    "J": (0, 80, 220),
    "L": (240, 150, 0),
    "BG": (15, 15, 20),
    "GRID": (40, 40, 50),
    "TEXT": (230, 230, 235),
    "SNAKE_HEAD": (60, 220, 120),
    "SNAKE_BODY": (40, 170, 90),
    "FOOD": (240, 80, 80),
}


class TetrisGame:
    # Classic-ish dimensions.
    GRID_W = 10
    GRID_H = 22  # includes 2 hidden rows at the top
    VISIBLE_TOP = 2
    VISIBLE_BOTTOM_EXCL = 22  # use [2..21]

    # Pieces: 4x4 matrices with unique rotations.
    PIECE_ORDER = ["I", "O", "T", "S", "Z", "J", "L"]
    PIECE_TO_INDEX = {k: i + 1 for i, k in enumerate(PIECE_ORDER)}

    BASE_MATS = {
        # Each is a 4x4 with 1s.
        "I": [
            [0, 0, 0, 0],
            [1, 1, 1, 1],
            [0, 0, 0, 0],
            [0, 0, 0, 0],
        ],
        "O": [
            [0, 1, 1, 0],
            [0, 1, 1, 0],
            [0, 0, 0, 0],
            [0, 0, 0, 0],
        ],
        "T": [
            [0, 1, 0, 0],
            [1, 1, 1, 0],
            [0, 0, 0, 0],
            [0, 0, 0, 0],
        ],
        "S": [
            [0, 1, 1, 0],
            [1, 1, 0, 0],
            [0, 0, 0, 0],
            [0, 0, 0, 0],
        ],
        "Z": [
            [1, 1, 0, 0],
            [0, 1, 1, 0],
            [0, 0, 0, 0],
            [0, 0, 0, 0],
        ],
        "J": [
            [1, 0, 0, 0],
            [1, 1, 1, 0],
            [0, 0, 0, 0],
            [0, 0, 0, 0],
        ],
        "L": [
            [0, 0, 1, 0],
            [1, 1, 1, 0],
            [0, 0, 0, 0],
            [0, 0, 0, 0],
        ],
    }

    def __init__(self) -> None:
        self.grid: List[List[int]] = [
            [0 for _ in range(self.GRID_W)] for _ in range(self.GRID_H)
        ]
        self.score = 0
        self.lines = 0
        self.level = 1

        self._bag: List[str] = []
        self._current_kind: Optional[str] = None
        self._rotations: List[List[List[int]]] = []
        self._rot_idx = 0
        self._piece_x = 3
        self._piece_y = -2

        self.game_over = False
        self.paused = False
        self.soft_dropping = False

        self._drop_accum = 0.0
        self._spawn_piece()

    def _refill_bag(self) -> None:
        self._bag = self.PIECE_ORDER[:]
        random.shuffle(self._bag)

    def _spawn_piece(self) -> None:
        if not self._bag:
            self._refill_bag()
        self._current_kind = self._bag.pop()
        self._rotations = unique_rotations(self.BASE_MATS[self._current_kind])
        self._rot_idx = 0
        self._piece_x = 3
        self._piece_y = -2

        # If it collides on spawn => game over.
        if self._collides(dx=0, dy=0, rot_idx=self._rot_idx):
            self.game_over = True

    def _blocks_for(self, x: int, y: int, rot_idx: int) -> List[Tuple[int, int]]:
        mat = self._rotations[rot_idx]
        blocks: List[Tuple[int, int]] = []
        for bx, by in matrix_to_blocks(mat):
            blocks.append((x + bx, y + by))
        return blocks

    def _collides(self, dx: int, dy: int, rot_idx: int) -> bool:
        if self._current_kind is None:
            return False
        x0 = self._piece_x + dx
        y0 = self._piece_y + dy
        for x, y in self._blocks_for(x0, y0, rot_idx):
            # Outside horizontal bounds always collides.
            if x < 0 or x >= self.GRID_W:
                return True
            # Below bottom => collides.
            if y >= self.GRID_H:
                return True
            # y can be negative (hidden rows); only collide with existing blocks for y >= 0.
            if y >= 0 and self.grid[y][x] != 0:
                return True
        return False

    def _lock_piece(self) -> None:
        assert self._current_kind is not None
        color_idx = self.PIECE_TO_INDEX[self._current_kind]
        for x, y in self._blocks_for(self._piece_x, self._piece_y, self._rot_idx):
            if y < 0:
                self.game_over = True
                return
            self.grid[y][x] = color_idx

        cleared = self._clear_lines()
        if cleared:
            # Simple scoring: 100/300/500/800 * level, like classic variants.
            base_scores = {1: 100, 2: 300, 3: 500, 4: 800}
            self.score += base_scores.get(cleared, 0) * self.level
            self.lines += cleared
            self.level = 1 + self.lines // 10

        self._spawn_piece()

    def _clear_lines(self) -> int:
        cleared = 0
        y = 0
        # Iterate top->bottom; remove full rows and insert empty row at top.
        while y < self.GRID_H:
            if all(self.grid[y][x] != 0 for x in range(self.GRID_W)):
                del self.grid[y]
                self.grid.insert(0, [0 for _ in range(self.GRID_W)])
                cleared += 1
                # Don't increment y, because new row at y needs checking.
            else:
                y += 1
        return cleared

    def _current_kind_color(self) -> Tuple[int, int, int]:
        assert self._current_kind is not None
        return COLORS[self._current_kind]

    def _try_move(self, dx: int, dy: int) -> bool:
        if self._collides(dx=dx, dy=dy, rot_idx=self._rot_idx):
            return False
        self._piece_x += dx
        self._piece_y += dy
        return True

    def _try_rotate(self) -> None:
        next_rot = (self._rot_idx + 1) % len(self._rotations)

        # Lightweight "wall kicks": try small horizontal offsets.
        for kick_x in (0, -1, 1, -2, 2):
            if not self._collides(dx=kick_x, dy=0, rot_idx=next_rot):
                self._rot_idx = next_rot
                self._piece_x += kick_x
                return

    def reset(self) -> None:
        self.__init__()

    def update(self, dt: float) -> None:
        if self.game_over or self.paused:
            return

        self._drop_accum += dt
        gravity = max(0.08, 0.8 * (0.9 ** (self.level - 1)))
        if self.soft_dropping:
            gravity *= 0.08  # much faster while holding Down

        while self._drop_accum >= gravity:
            self._drop_accum -= gravity
            # If we can't move down, lock and spawn next.
            if not self._try_move(dx=0, dy=1):
                self._lock_piece()
                return

    def handle_keydown(self, key: int) -> None:
        if key == pygame.K_p:
            self.paused = not self.paused
            return
        if self.game_over:
            return
        if key == pygame.K_LEFT:
            self._try_move(-1, 0)
        elif key == pygame.K_RIGHT:
            self._try_move(1, 0)
        elif key == pygame.K_DOWN:
            self.soft_dropping = True
        elif key in (pygame.K_UP, pygame.K_x):
            self._try_rotate()
        elif key == pygame.K_SPACE:
            self.hard_drop()

    def handle_keyup(self, key: int) -> None:
        if key == pygame.K_DOWN:
            self.soft_dropping = False

    def hard_drop(self) -> None:
        if self.game_over:
            return
        while self._try_move(dx=0, dy=1):
            pass
        self._lock_piece()

    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        screen.fill(COLORS["BG"])

        cell = 24
        origin_x = 40
        origin_y = 40
        panel_x = origin_x + self.GRID_W * cell + 40

        # Draw static grid background (visible portion only).
        for gy in range(self.VISIBLE_TOP, self.GRID_H):
            for gx in range(self.GRID_W):
                rect = pygame.Rect(
                    origin_x + gx * cell,
                    origin_y + (gy - self.VISIBLE_TOP) * cell,
                    cell,
                    cell,
                )
                pygame.draw.rect(screen, COLORS["GRID"], rect, width=1)

        # Draw locked blocks.
        for gy in range(self.VISIBLE_TOP, self.GRID_H):
            row = self.grid[gy]
            for gx in range(self.GRID_W):
                v = row[gx]
                if v == 0:
                    continue
                kind = self.PIECE_ORDER[v - 1]
                color = COLORS[kind]
                rect = pygame.Rect(
                    origin_x + gx * cell,
                    origin_y + (gy - self.VISIBLE_TOP) * cell,
                    cell,
                    cell,
                )
                pygame.draw.rect(screen, color, rect.inflate(-3, -3))

        # Draw current moving piece.
        if not self.game_over:
            assert self._current_kind is not None
            piece_color = self._current_kind_color()
            for x, y in self._blocks_for(self._piece_x, self._piece_y, self._rot_idx):
                if y < self.VISIBLE_TOP or y >= self.GRID_H:
                    continue
                rect = pygame.Rect(
                    origin_x + x * cell,
                    origin_y + (y - self.VISIBLE_TOP) * cell,
                    cell,
                    cell,
                )
                pygame.draw.rect(screen, piece_color, rect.inflate(-3, -3))

        # Panel
        def draw_text(lines: Sequence[str], y0: int) -> None:
            y = y0
            for line in lines:
                surf = font.render(line, True, COLORS["TEXT"])
                screen.blit(surf, (panel_x, y))
                y += 28

        draw_text(
            [
                "TETRIS",
                "",
                f"Score: {self.score}",
                f"Lines: {self.lines}",
                f"Level: {self.level}",
                "",
                "Controls:",
                "Left/Right: move",
                "Down: soft drop",
                "Up/X: rotate",
                "Space: hard drop",
                "P: pause",
                "",
                "ESC: menu",
            ],
            y0=60,
        )

        if self.paused and not self.game_over:
            _draw_center_message(
                screen, font, "Paused", "Press P to resume"
            )
        if self.game_over:
            _draw_center_message(screen, font, "Game Over", "Press R to restart")


class SnakeGame:
    def __init__(self, grid_size: int = 20) -> None:
        self.grid_size = grid_size
        self.cell = 24

        self.score = 0
        self.game_over = False
        self.paused = False

        self._move_accum = 0.0
        self._base_moves_per_sec = 8.0
        self._target_dir: Vec2 = (1, 0)
        self._dir: Vec2 = (1, 0)

        mid = grid_size // 2
        self.snake: List[Vec2] = [(mid, mid), (mid - 1, mid), (mid - 2, mid)]
        self._place_food()

    def reset(self) -> None:
        self.__init__(grid_size=self.grid_size)

    def _random_empty_cell(self) -> Vec2:
        empty = [(x, y) for x in range(self.grid_size) for y in range(self.grid_size)]
        snake_set = set(self.snake)
        empty = [p for p in empty if p not in snake_set]
        return random.choice(empty)

    def _place_food(self) -> None:
        self.food: Vec2 = self._random_empty_cell()

    def _moves_per_sec(self) -> float:
        # Increase speed gradually with score.
        return self._base_moves_per_sec + (self.score // 5) * 1.2

    def _tick(self) -> None:
        if self.game_over or self.paused:
            return

        # Apply direction at tick time (prevents "instant reverse").
        dx, dy = self._target_dir
        self._dir = (dx, dy)

        hx, hy = self.snake[0]
        nx, ny = hx + dx, hy + dy

        # Wall collision.
        if nx < 0 or nx >= self.grid_size or ny < 0 or ny >= self.grid_size:
            self.game_over = True
            return

        new_head = (nx, ny)
        # Self collision: moving into current tail cell is allowed only if tail moves away.
        # We'll do the simple and safe version: treat any overlap as collision (standard in arcade Snake).
        if new_head in self.snake:
            self.game_over = True
            return

        self.snake.insert(0, new_head)
        if new_head == self.food:
            self.score += 1
            self._place_food()
        else:
            self.snake.pop()

    def update(self, dt: float) -> None:
        if self.game_over or self.paused:
            return

        moves_per_sec = self._moves_per_sec()
        self._move_accum += dt
        interval = 1.0 / moves_per_sec
        while self._move_accum >= interval:
            self._move_accum -= interval
            self._tick()
            if self.game_over:
                return

    def handle_keydown(self, key: int) -> None:
        if key == pygame.K_p:
            self.paused = not self.paused
            return
        if self.game_over:
            return

        # Direction input with no reverse.
        if key in (pygame.K_LEFT, pygame.K_a):
            self._set_dir_no_reverse((-1, 0))
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self._set_dir_no_reverse((1, 0))
        elif key in (pygame.K_UP, pygame.K_w):
            self._set_dir_no_reverse((0, -1))
        elif key in (pygame.K_DOWN, pygame.K_s):
            self._set_dir_no_reverse((0, 1))

    def _set_dir_no_reverse(self, nd: Vec2) -> None:
        # Prevent reversing directly into yourself.
        if (nd[0] == -self._dir[0]) and (nd[1] == -self._dir[1]):
            return
        self._target_dir = nd

    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        screen.fill(COLORS["BG"])

        board_px = self.grid_size * self.cell
        origin_x = 40
        origin_y = 40
        panel_x = origin_x + board_px + 40

        # Background grid
        board_rect = pygame.Rect(origin_x, origin_y, board_px, board_px)
        pygame.draw.rect(screen, COLORS["GRID"], board_rect, width=2)

        for x in range(self.grid_size):
            for y in range(self.grid_size):
                # subtle grid lines
                r = pygame.Rect(
                    origin_x + x * self.cell,
                    origin_y + y * self.cell,
                    self.cell,
                    self.cell,
                )
                pygame.draw.rect(screen, COLORS["GRID"], r, width=1)

        # Food
        fx, fy = self.food
        food_rect = pygame.Rect(
            origin_x + fx * self.cell + 4,
            origin_y + fy * self.cell + 4,
            self.cell - 8,
            self.cell - 8,
        )
        pygame.draw.ellipse(screen, COLORS["FOOD"], food_rect)

        # Snake
        for i, (sx, sy) in enumerate(self.snake):
            rect = pygame.Rect(
                origin_x + sx * self.cell + 3,
                origin_y + sy * self.cell + 3,
                self.cell - 6,
                self.cell - 6,
            )
            color = COLORS["SNAKE_HEAD"] if i == 0 else COLORS["SNAKE_BODY"]
            pygame.draw.rect(screen, color, rect, border_radius=6)

        # Panel text
        def draw_text(lines: Sequence[str], y0: int) -> None:
            y = y0
            for line in lines:
                surf = font.render(line, True, COLORS["TEXT"])
                screen.blit(surf, (panel_x, y))
                y += 28

        draw_text(
            [
                "SNAKE",
                "",
                f"Score: {self.score}",
                "",
                "Controls:",
                "Arrow keys / WASD",
                "P: pause",
                "",
                "ESC: menu",
            ],
            y0=60,
        )

        if self.paused and not self.game_over:
            _draw_center_message(screen, font, "Paused", "Press P to resume")
        if self.game_over:
            _draw_center_message(screen, font, "Game Over", "Press R to restart")


def _draw_center_message(
    screen: pygame.Surface, font: pygame.font.Font, title: str, subtitle: Optional[str] = None
) -> None:
    w, h = screen.get_size()
    title_s = font.render(title, True, COLORS["TEXT"])
    title_x = (w - title_s.get_width()) // 2
    title_y = h // 2 - (subtitle and 18 or 0)
    screen.blit(title_s, (title_x, title_y - 22))
    if subtitle:
        sub_s = font.render(subtitle, True, COLORS["TEXT"])
        sub_x = (w - sub_s.get_width()) // 2
        screen.blit(sub_s, (sub_x, title_y + 10))


def draw_title_screen(screen: pygame.Surface, font: pygame.font.Font) -> None:
    screen.fill(COLORS["BG"])
    w, h = screen.get_size()

    lines = [
        "Tetris + Snake",
        "",
        "Press 1 for Tetris",
        "Press 2 for Snake",
        "ESC to quit",
    ]
    y = h // 2 - 80
    for line in lines:
        surf = font.render(line, True, COLORS["TEXT"])
        screen.blit(surf, ((w - surf.get_width()) // 2, y))
        y += 30

    hint = font.render("Tip: use arrow keys / WASD for Snake", True, COLORS["TEXT"])
    screen.blit(hint, ((w - hint.get_width()) // 2, y + 20))


def run_tetris(screen: pygame.Surface, clock: pygame.time.Clock) -> None:
    # Resize window for tetris.
    cell = 24
    board_w = TetrisGame.GRID_W * cell
    board_h = TetrisGame.GRID_H * cell
    panel_w = 240
    origin_x = 40
    origin_y = 40
    screen = pygame.display.set_mode(
        (origin_x * 2 + board_w + panel_w, origin_y * 2 + board_h)
    )
    font = pygame.font.SysFont(None, 28)
    game = TetrisGame()

    while True:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return
                if game.game_over:
                    if event.key == pygame.K_r:
                        game.reset()
                    continue
                game.handle_keydown(event.key)
            if event.type == pygame.KEYUP:
                game.handle_keyup(event.key)

        game.update(dt)
        game.draw(screen, font)
        pygame.display.flip()


def run_snake(screen: pygame.Surface, clock: pygame.time.Clock) -> None:
    grid_size = 20
    cell = 24
    board_px = grid_size * cell
    origin_x = 40
    origin_y = 40
    panel_w = 240
    screen = pygame.display.set_mode(
        (origin_x * 2 + board_px + panel_w, origin_y * 2 + board_px)
    )
    font = pygame.font.SysFont(None, 28)
    game = SnakeGame(grid_size=grid_size)

    while True:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return
                if game.game_over:
                    if event.key == pygame.K_r:
                        game.reset()
                    continue
                game.handle_keydown(event.key)

        game.update(dt)
        game.draw(screen, font)
        pygame.display.flip()


def main() -> None:
    pygame.init()
    pygame.display.set_caption("Tetris + Snake")
    clock = pygame.time.Clock()

    screen = pygame.display.set_mode((900, 600))
    font = pygame.font.SysFont(None, 36)

    while True:
        draw_title_screen(screen, font)
        pygame.display.flip()

        # Wait for a selection.
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    return
                if event.key == pygame.K_1:
                    run_tetris(screen, clock)
                elif event.key == pygame.K_2:
                    run_snake(screen, clock)

        clock.tick(30)


if __name__ == "__main__":
    main()

