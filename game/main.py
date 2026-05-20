import asyncio
import pygame
import sys
import math
import random
import traceback
from abc import ABC, abstractmethod
from typing import Optional

pygame.init()
pygame.key.set_repeat(220, 110)   # 홀드 시 220ms 후 110ms 간격으로 반복

# ── 화면 ──────────────────────────────────────────
SCREEN_W, SCREEN_H = 1280, 720
screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
pygame.display.set_caption("4×4  Stage 1")
clock = pygame.time.Clock()

# ── 색상 ──────────────────────────────────────────
BG      = (8, 8, 8)
GC      = (55, 55, 55)
GB      = (82, 82, 82)
OBS     = (115, 115, 115)
CHAIN_C = (95, 95, 95)
TXT     = (125, 125, 125)

P_BLUE  = (78, 108, 220)
P_GREEN = (76, 196, 110)
P_RED   = (186, 52, 52)

# ── 그리드 ────────────────────────────────────────
CELL    = 80
COLS = ROWS = 4
GRID_PX = CELL * COLS
GRID_X  = (SCREEN_W - GRID_PX) // 2   # 480
GRID_Y  = (SCREEN_H - GRID_PX) // 2   # 200
GCX     = GRID_X + GRID_PX // 2       # 640
GCY     = GRID_Y + GRID_PX // 2       # 360

TOTAL    = 180.0
PR       = 24   # 플레이어 반지름
OR       = 22   # 장애물 공 반지름 (기본)
FLAIL_R  = 20   # 패턴3 철퇴 공 반지름
DIAG_R_BIG   = 36
DIAG_R_SMALL = 18

P_BREAKS = [31, 65, 87, 110, 139, 180]

# 스프링 상수
SPRING_K    = 950.0
SPRING_DAMP = 50.0

# 대각선 상수
_INV_SQRT2 = 1.0 / math.sqrt(2)
_DIAG_C    = [1160, 1000, 840]
_DIAG_DIR  = {
    1160: (-_INV_SQRT2,  _INV_SQRT2),
    1000: (-_INV_SQRT2,  _INV_SQRT2),
     840: ( _INV_SQRT2, -_INV_SQRT2),
}


def cell_center(col, row):
    return (GRID_X + col * CELL + CELL // 2,
            GRID_Y + row * CELL + CELL // 2)


# ══════════════════════════════════════════════════
# 플레이어
# ══════════════════════════════════════════════════
class Player:
    LIFE_COLORS = {3: P_BLUE, 2: P_GREEN, 1: P_RED}

    def __init__(self):
        self.col   = 1
        self.row   = 2
        self.lives = 3
        self.inv   = 0.0

        tx, ty = cell_center(1, 2)
        self.px  = float(tx)
        self.py  = float(ty)
        self.pvx = 0.0
        self.pvy = 0.0

        # trail: [x, y, 잔여시간, 반지름비율(0~1)]
        self.trail = []

    @property
    def color(self):
        return self.LIFE_COLORS.get(max(self.lives, 1), P_RED)

    @property
    def center(self):
        return (int(self.px), int(self.py))

    def move(self, dc, dr):
        self.trail.append([self.px, self.py, 0.28, 0.72])

        prev_col, prev_row = self.col, self.row
        self.col = (self.col + dc) % COLS
        self.row = (self.row + dr) % ROWS
        tx, ty = cell_center(self.col, self.row)

        wrapped_x = dc != 0 and abs(self.col - prev_col) != abs(dc)
        wrapped_y = dr != 0 and abs(self.row - prev_row) != abs(dr)

        if wrapped_x:
            for i in range(5):
                gx = self.px + dc * CELL * (0.45 + i * 0.55)
                fade = max(0.03, 0.22 - i * 0.04)
                self.trail.append([gx, self.py, fade, 0.65 - i * 0.1])
            self.px  = tx - dc * CELL * 1.3
            self.pvx = 0.0

        if wrapped_y:
            for i in range(5):
                gy = self.py + dr * CELL * (0.45 + i * 0.55)
                fade = max(0.03, 0.22 - i * 0.04)
                self.trail.append([self.px, gy, fade, 0.65 - i * 0.1])
            self.py  = ty - dr * CELL * 1.3
            self.pvy = 0.0

    def hit(self):
        if self.inv > 0:
            return False
        self.lives -= 1
        self.inv = 2.0
        return True

    def update(self, dt):
        self.inv = max(0.0, self.inv - dt)

        tx, ty = cell_center(self.col, self.row)
        ax = (tx - self.px) * SPRING_K - self.pvx * SPRING_DAMP
        ay = (ty - self.py) * SPRING_K - self.pvy * SPRING_DAMP
        self.pvx += ax * dt
        self.pvy += ay * dt
        self.px  += self.pvx * dt
        self.py  += self.pvy * dt

        self.trail = [[x, y, t - dt, r] for x, y, t, r in self.trail if t > dt]

    def draw(self, surface):
        for x, y, t, r_ratio in self.trail:
            alpha = int(160 * (t / 0.28) ** 1.8)
            r = max(2, int(PR * r_ratio))
            s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (*self.color, alpha), (r, r), r)
            surface.blit(s, (int(x) - r, int(y) - r))

        if self.inv > 0 and int(self.inv * 10) % 2 == 0:
            return
        pygame.draw.circle(surface, self.color, (int(self.px), int(self.py)), PR)


# ══════════════════════════════════════════════════
# 추상 기반 클래스 계층
# ══════════════════════════════════════════════════

class Obstacle(ABC):
    """모든 장애물의 공통 인터페이스 (추상 기반 클래스).

    캡슐화: 각 서브클래스가 자신의 위치·상태를 직접 관리한다.
    다형성: Stage1/Pattern은 구체 타입을 몰라도 update/draw/collides를 호출할 수 있다.
    """

    @abstractmethod
    def update(self, dt: float) -> None:
        """물리/애니메이션 상태를 dt 초 만큼 갱신한다."""
        ...

    @abstractmethod
    def draw(self, surface) -> None:
        """화면에 자신을 그린다."""
        ...

    @abstractmethod
    def collides(self, px: float, py: float) -> bool:
        """플레이어 좌표 (px, py)와 충돌 여부를 반환한다."""
        ...


class ActiveObstacle(Obstacle, ABC):
    """화면 밖으로 나가면 비활성화되는 장애물의 공통 기반.

    상속: Obstacle의 인터페이스를 물려받으면서 active 플래그와
          화면 이탈 비활성화 헬퍼(_deactivate_if_oob)를 추가로 제공한다.
    """

    def __init__(self):
        self.active: bool = True

    def _deactivate_if_oob(self, x: float, y: float, margin: int = 180) -> None:
        """(x, y)가 화면+margin 영역 밖이면 active=False로 설정한다."""
        if not (-margin < x < SCREEN_W + margin and
                -margin < y < SCREEN_H + margin):
            self.active = False


# ══════════════════════════════════════════════════
# 패턴 1: 직선 공  (ActiveObstacle 상속)
# ══════════════════════════════════════════════════
class StraightBall(ActiveObstacle):
    def __init__(self, x, y, vx, vy):
        super().__init__()
        self.x, self.y = float(x), float(y)
        self.vx, self.vy = vx, vy

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self._deactivate_if_oob(self.x, self.y, margin=180)

    def draw(self, surface) -> None:
        pygame.draw.circle(surface, OBS, (int(self.x), int(self.y)), OR)

    def collides(self, px: float, py: float) -> bool:
        return math.hypot(self.x - px, self.y - py) < OR + PR - 4


# ══════════════════════════════════════════════════
# 패턴 2: 오비터  (Obstacle 상속)
# ══════════════════════════════════════════════════
class Orbiter(Obstacle):
    """중심점을 기준으로 공전하는 장애물.
    active 플래그 없이 항상 존재하며, 등장 연출(fade-in)을 자체적으로 관리한다.
    """
    INTRO_DUR = 2.8

    def __init__(self, cx, cy, arm, angle, omega_target, delay=0.0):
        self.cx, self.cy    = cx, cy
        self.arm            = arm
        self.angle          = angle
        self.omega_target   = omega_target
        self.delay          = delay
        self.intro_t        = -delay
        self.hist           = []

    @property
    def _ratio(self) -> float:
        return max(0.0, min(1.0, self.intro_t / self.INTRO_DUR))

    @property
    def alpha_byte(self) -> int:
        return int(self._ratio * 255)

    @property
    def current_omega(self) -> float:
        r = self._ratio
        return self.omega_target * r * r

    @property
    def pos(self):
        return (self.cx + math.cos(self.angle) * self.arm,
                self.cy + math.sin(self.angle) * self.arm)

    def update(self, dt: float) -> None:
        self.intro_t += dt
        if self.intro_t > 0:
            self.angle += self.current_omega * dt
            if self.intro_t > 0.6:
                self.hist.append(self.pos)
                if len(self.hist) > 72:
                    self.hist.pop(0)

    def draw(self, surface) -> None:
        a = self._ratio
        if a <= 0.01:
            return
        ab = self.alpha_byte

        n = len(self.hist)
        for i, (hx, hy) in enumerate(self.hist):
            ratio = (i + 1) / (n + 1)
            trail_a = int(145 * ratio ** 2 * a)
            r = max(3, int(OR * ratio * 0.85))
            s = pygame.Surface((r * 2 + 1, r * 2 + 1), pygame.SRCALPHA)
            pygame.draw.circle(s, (*OBS, trail_a), (r, r), r)
            surface.blit(s, (int(hx) - r, int(hy) - r))

        px, py = self.pos
        s = pygame.Surface((OR * 2 + 1, OR * 2 + 1), pygame.SRCALPHA)
        pygame.draw.circle(s, (*OBS, ab), (OR, OR), OR)
        surface.blit(s, (int(px) - OR, int(py) - OR))

    def collides(self, px: float, py: float) -> bool:
        if self._ratio < 1.0:
            return False
        bx, by = self.pos
        return math.hypot(bx - px, by - py) < OR + PR - 4


# ══════════════════════════════════════════════════
# 패턴 3: 철퇴  (Obstacle 상속)
# ══════════════════════════════════════════════════
class Flail(Obstacle):
    """앵커에서 체인으로 매달린 진자운동 장애물.
    고정점이 화면 위쪽(-160)에 있어 active 플래그 없이 항상 유지된다.
    """
    _BALL_C  = (175, 175, 175)
    _CHAIN_C = (130, 130, 130)

    def __init__(self, ax, ay, arm, phase, omega, amplitude=None):
        self.ax, self.ay  = ax, ay
        self.arm          = arm
        self.phase        = phase
        self.omega        = omega
        self.amplitude    = amplitude

    @property
    def ball(self):
        if self.amplitude is not None:
            a = self.amplitude * math.sin(self.phase)
            return (self.ax + self.arm * math.sin(a),
                    self.ay + self.arm * math.cos(a))
        return (self.ax + math.cos(self.phase) * self.arm,
                self.ay + math.sin(self.phase) * self.arm)

    def update(self, dt: float) -> None:
        self.phase += self.omega * dt

    def draw(self, surface) -> None:
        bx, by = self.ball
        if not (-FLAIL_R * 2 < bx < SCREEN_W + FLAIL_R * 2 and
                -FLAIL_R * 2 < by < SCREEN_H + FLAIL_R * 2):
            return
        dx, dy = bx - self.ax, by - self.ay
        dist   = math.hypot(dx, dy)
        n_link = max(1, int(dist / 12))
        for i in range(1, n_link + 1):
            t  = i / (n_link + 1)
            lx = self.ax + dx * t
            ly = self.ay + dy * t
            if -10 < lx < SCREEN_W + 10 and -10 < ly < SCREEN_H + 10:
                ls = pygame.Surface((16, 9), pygame.SRCALPHA)
                pygame.draw.ellipse(ls, (*self._CHAIN_C, 220), (0, 0, 16, 9))
                surface.blit(ls, (int(lx) - 8, int(ly) - 4))
        ibx, iby = int(bx), int(by)
        pygame.draw.circle(surface, self._BALL_C, (ibx, iby), FLAIL_R)
        d = int(FLAIL_R * 0.62)
        for k in range(4):
            a  = math.pi / 4 * k
            x1 = ibx + int(math.cos(a) * d)
            y1 = iby + int(math.sin(a) * d)
            pygame.draw.line(surface, (80, 80, 80),
                             (x1, y1), (ibx - (x1 - ibx), iby - (y1 - iby)), 2)

    def collides(self, px: float, py: float) -> bool:
        bx, by = self.ball
        return math.hypot(bx - px, by - py) < FLAIL_R + PR - 4


# ══════════════════════════════════════════════════
# 패턴 4: 대각선 롤러  (ActiveObstacle 상속)
# ══════════════════════════════════════════════════
class DiagBall(ActiveObstacle):
    """대각선을 따라 구르며 이동하는 장애물.
    visual_pos 프로퍼티로 실제 경로(선)와 시각적 위치(수직 오프셋)를 분리한다.
    """
    BASE_SPEED = 212.0
    ACCEL      = 90.0
    MAX_SPEED  = 800.0

    def __init__(self, x, y, nx, ny, big=None):
        super().__init__()
        self.x, self.y   = float(x), float(y)
        self.nx, self.ny = nx, ny
        self.spin        = random.uniform(0, math.pi * 2)
        self.radius = DIAG_R_BIG if (big if big is not None else random.random() < 0.35) else DIAG_R_SMALL
        self.speed  = self.BASE_SPEED

    @property
    def visual_pos(self):
        """경사면 구름: 선(x+y=c)의 위쪽 면에서 radius 만큼 수직으로 고정 이동."""
        off = self.radius * _INV_SQRT2
        return (self.x - off, self.y - off)

    def update(self, dt: float) -> None:
        self.speed = min(self.speed + self.ACCEL * dt, self.MAX_SPEED)
        dist = self.speed * dt
        self.x += self.nx * dist
        self.y += self.ny * dist
        self.spin += math.copysign(dist / self.radius, -self.nx)
        self._deactivate_if_oob(self.x, self.y, margin=260)

    _BALL_C = (168, 168, 168)

    def draw(self, surface) -> None:
        vx, vy = self.visual_pos
        ix, iy = int(vx), int(vy)
        r = self.radius
        pygame.draw.circle(surface, self._BALL_C, (ix, iy), r)
        for i in range(3):
            a  = self.spin + math.pi * 2 * i / 3
            x1 = ix + int(math.cos(a)           * (r - 2))
            y1 = iy + int(math.sin(a)           * (r - 2))
            x2 = ix + int(math.cos(a + math.pi) * (r // 2))
            y2 = iy + int(math.sin(a + math.pi) * (r // 2))
            pygame.draw.line(surface, (60, 60, 60), (x1, y1), (x2, y2), 2)

    def collides(self, px: float, py: float) -> bool:
        vx, vy = self.visual_pos
        return math.hypot(vx - px, vy - py) < self.radius + PR - 4


# ══════════════════════════════════════════════════
# 패턴 5: 발사대 & 발사체
# ══════════════════════════════════════════════════
class Emitter:
    """원형 배치 발사대. Obstacle 서브클래스가 아님 — 직접 충돌판정 없음."""
    R = OR

    def __init__(self, x, y, idx: int = 0):
        self.x, self.y = x, y
        self.idx = idx

    def draw(self, surface) -> None:
        pygame.draw.circle(surface, OBS, (int(self.x), int(self.y)), self.R)
        pygame.draw.circle(surface,
                           (OBS[0] // 2, OBS[1] // 2, OBS[2] // 2),
                           (int(self.x), int(self.y)), self.R, 2)


class Projectile(ActiveObstacle):
    """발사대에서 목표 발사대로 날아가는 발사체 (ActiveObstacle 상속)."""

    def __init__(self, x, y, vx, vy, target: Optional[Emitter] = None):
        super().__init__()
        self.x, self.y   = float(x), float(y)
        self.vx, self.vy = vx, vy
        self.target      = target

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.target is not None:
            if math.hypot(self.x - self.target.x,
                          self.y - self.target.y) < OR + Emitter.R - 2:
                self.active = False
                return
        self._deactivate_if_oob(self.x, self.y, margin=120)

    def draw(self, surface) -> None:
        pygame.draw.circle(surface, OBS, (int(self.x), int(self.y)), OR)

    def collides(self, px: float, py: float) -> bool:
        return math.hypot(self.x - px, self.y - py) < OR + PR - 4


# ══════════════════════════════════════════════════
# 패턴 6: 벽 튕김 공  (Obstacle 상속)
# ══════════════════════════════════════════════════
class BounceBall(Obstacle):
    """화면 경계에서 반사하며 영구적으로 존재하는 장애물."""

    def __init__(self, x, y, vx, vy):
        self.x, self.y   = float(x), float(y)
        self.vx, self.vy = vx, vy

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.x - OR < 0:
            self.x = float(OR);       self.vx = abs(self.vx)
        elif self.x + OR > SCREEN_W:
            self.x = float(SCREEN_W - OR); self.vx = -abs(self.vx)
        if self.y - OR < 0:
            self.y = float(OR);       self.vy = abs(self.vy)
        elif self.y + OR > SCREEN_H:
            self.y = float(SCREEN_H - OR); self.vy = -abs(self.vy)

    def draw(self, surface) -> None:
        pygame.draw.circle(surface, OBS, (int(self.x), int(self.y)), OR)

    def collides(self, px: float, py: float) -> bool:
        return math.hypot(self.x - px, self.y - py) < OR + PR - 4


# ══════════════════════════════════════════════════
# 그리드 & 배경
# ══════════════════════════════════════════════════
def draw_grid(surface):
    for i in range(1, COLS):
        x = GRID_X + i * CELL
        pygame.draw.line(surface, GC, (x, GRID_Y), (x, GRID_Y + GRID_PX), 1)
    for j in range(1, ROWS):
        y = GRID_Y + j * CELL
        pygame.draw.line(surface, GC, (GRID_X, y), (GRID_X + GRID_PX, y), 1)
    pygame.draw.rect(surface, GB,
                     pygame.Rect(GRID_X, GRID_Y, GRID_PX, GRID_PX), 2)


def draw_diag_bg(surface, alpha=32):
    """그리드 대각선 3개 그리기 (x+y = 1160, 1000, 840)"""
    s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    for c in _DIAG_C:
        x1, y1 = c, 0
        x2, y2 = c - SCREEN_H, SCREEN_H
        pygame.draw.line(s, (200, 200, 200, alpha), (x1, y1), (x2, y2), 2)
    surface.blit(s, (0, 0))


# ══════════════════════════════════════════════════
# 패턴 추상 기반 클래스
# ══════════════════════════════════════════════════
class Pattern(ABC):
    """각 패턴의 공통 인터페이스 및 공유 로직 (추상 기반 클래스).

    캡슐화: 패턴별 타이머·장애물 목록·스폰 로직이 각 서브클래스 안에 완전히 은닉된다.
    다형성: Stage1은 Pattern 인터페이스만 사용하며 구체 패턴 클래스에 의존하지 않는다.
    """

    def __init__(self):
        self.p_timer:    float = 0.0
        self.spawn_timer: float = 0.0

    def _tick(self, dt: float) -> None:
        """공통 타이머 진행."""
        self.p_timer    += dt
        self.spawn_timer += dt

    @staticmethod
    def _process_active(obstacles: list, dt: float, player,
                        remove_on_hit: bool = True) -> list:
        """ActiveObstacle 목록을 일괄 처리하는 정적 유틸리티.

        1. 각 장애물 update
        2. 충돌 시 player.hit() 호출, remove_on_hit=True이면 비활성화
        3. active인 것만 필터링하여 반환
        """
        px, py = player.center
        for ob in obstacles:
            ob.update(dt)
            if ob.active and ob.collides(px, py):
                if player.hit() and remove_on_hit:
                    ob.active = False
        return [ob for ob in obstacles if ob.active]

    @abstractmethod
    def update(self, dt: float, player) -> None:
        """패턴 상태를 갱신한다."""
        ...

    @abstractmethod
    def draw(self, surface) -> None:
        """패턴 장애물을 그린다."""
        ...


# ══════════════════════════════════════════════════
# Pattern0: 직선 공
# ══════════════════════════════════════════════════
class Pattern0(Pattern):
    """직선 공을 일정 간격으로 스폰한다.
    is_clearing 플래그가 True이면 새 공을 스폰하지 않고 기존 공이 빠질 때까지 대기한다.
    """

    def __init__(self):
        super().__init__()
        self._balls:      list[StraightBall] = []
        self._spawn_hist: list[str] = []
        self.is_clearing: bool = False

    @property
    def is_empty(self) -> bool:
        """화면에 남은 공이 없으면 True."""
        return len(self._balls) == 0

    def update(self, dt: float, player) -> None:
        self._tick(dt)

        if not self.is_clearing:
            spawn_iv = max(0.42, 0.85 - self.p_timer * 0.014)
            if self.spawn_timer >= spawn_iv:
                self.spawn_timer = 0.0
                self._spawn_straight()

        self._balls = Pattern._process_active(self._balls, dt, player)

    def draw(self, surface) -> None:
        for b in self._balls:
            b.draw(surface)

    # ── 스폰 로직 (캡슐화) ─────────────────────────
    def _spawn_straight(self) -> None:
        speed = 260 + self.p_timer * 1.2
        last = self._spawn_hist[-3:]
        if len(last) == 3 and all(d == 'h' for d in last):
            horiz = False
        elif len(last) == 3 and all(d == 'v' for d in last):
            horiz = True
        else:
            horiz = random.random() < 0.5

        if horiz:
            row = random.randint(0, ROWS - 1)
            y   = GRID_Y + row * CELL + CELL // 2
            if random.random() < 0.5:
                self._balls.append(StraightBall(-OR - 5, y,  speed, 0))
            else:
                self._balls.append(StraightBall(SCREEN_W + OR + 5, y, -speed, 0))
        else:
            col = random.randint(0, COLS - 1)
            x   = GRID_X + col * CELL + CELL // 2
            if random.random() < 0.5:
                self._balls.append(StraightBall(x, -OR - 5, 0,  speed))
            else:
                self._balls.append(StraightBall(x, SCREEN_H + OR + 5, 0, -speed))

        self._spawn_hist.append('h' if horiz else 'v')
        if len(self._spawn_hist) > 12:
            self._spawn_hist.pop(0)


# ══════════════════════════════════════════════════
# Pattern1: 오비터
# ══════════════════════════════════════════════════
class Pattern1(Pattern):
    """8개의 Orbiter를 fade-in + 가속으로 등장시킨다."""

    def __init__(self):
        super().__init__()
        self._orbiters: list[Orbiter] = []
        configs = [
            (GRID_X - 160,                GCY,                        300,  1.20, 0.0),
            (GRID_X + GRID_PX + 160,      GCY,                        285, -1.04, 0.5),
            (GCX,                         GRID_Y - 155,               275,  1.36, 1.0),
            (GCX,                         GRID_Y + GRID_PX + 155,     265, -1.26, 1.5),
            (GRID_X - 115,                GRID_Y - 115,               255,  0.92, 2.0),
            (GRID_X + GRID_PX + 115,      GRID_Y - 115,               250, -1.12, 2.5),
            (GRID_X - 115,                GRID_Y + GRID_PX + 115,     248,  1.02, 3.0),
            (GRID_X + GRID_PX + 115,      GRID_Y + GRID_PX + 115,     258, -1.40, 3.5),
        ]
        for cx, cy, arm, omega, delay in configs:
            ang = random.uniform(0, math.pi * 2)
            self._orbiters.append(Orbiter(cx, cy, arm, ang, omega, delay))

    def update(self, dt: float, player) -> None:
        px, py = player.center
        for ob in self._orbiters:
            ob.update(dt)
            if ob.collides(px, py):
                player.hit()

    def draw(self, surface) -> None:
        for ob in self._orbiters:
            ob.draw(surface)


# ══════════════════════════════════════════════════
# Pattern2: 철퇴
# ══════════════════════════════════════════════════
class Pattern2(Pattern):
    """진자운동 철퇴 6개. 앵커 y=-160, 행별 1/2/2/1 비대칭 배치."""

    def __init__(self):
        super().__init__()
        self._flails: list[Flail] = []
        AY = -160
        pend_cfgs = [
            (AY, 400, 1.10, 0.72, 0.0),
            (AY, 480, 1.18, 0.87, 0.4),
            (AY, 480, 1.22, 0.92, 2.5),
            (AY, 560, 1.25, 1.01, 1.1),
            (AY, 560, 1.28, 1.07, 3.7),
            (AY, 640, 1.32, 1.20, 1.8),
        ]
        for ay, arm, amp, omega, phase in pend_cfgs:
            self._flails.append(Flail(GCX, ay, arm, phase, omega, amplitude=amp))

    def update(self, dt: float, player) -> None:
        px, py = player.center
        for f in self._flails:
            f.update(dt)
            if f.collides(px, py):
                player.hit()

    def draw(self, surface) -> None:
        for f in self._flails:
            f.draw(surface)


# ══════════════════════════════════════════════════
# Pattern3: 대각선 롤러
# ══════════════════════════════════════════════════
class Pattern3(Pattern):
    """대각선 3개 위에서 교대로 등장하는 구름 공.
    draw()에서 대각선 배경도 함께 그린다(Pattern 내부에 시각 책임 캡슐화).
    """

    def __init__(self):
        super().__init__()
        self._balls:       list[DiagBall] = []
        self._last_diag_c: Optional[int]  = None
        self._spawn_iv: float = random.uniform(0.55, 1.0)
        self._spawn_one()

    def update(self, dt: float, player) -> None:
        self._tick(dt)
        if self.spawn_timer >= self._spawn_iv:
            self.spawn_timer = 0.0
            self._spawn_iv   = random.uniform(0.55, 1.0)
            self._spawn_one()
        self._balls = Pattern._process_active(self._balls, dt, player)

    def draw(self, surface) -> None:
        draw_diag_bg(surface)
        for b in self._balls:
            b.draw(surface)

    def _spawn_one(self) -> None:
        candidates = [c for c in _DIAG_C if c != self._last_diag_c]
        if not candidates:
            candidates = list(_DIAG_C)
        c = random.choice(candidates)
        self._last_diag_c = c

        nx, ny = _DIAG_DIR[c]
        off    = DIAG_R_BIG * _INV_SQRT2
        margin = int(off) + DIAG_R_BIG + 30
        if nx < 0:
            y = -margin - random.uniform(0, 40)
        else:
            y = SCREEN_H + margin + random.uniform(0, 40)
        x = c - y
        self._balls.append(DiagBall(x, y, nx, ny))


# ══════════════════════════════════════════════════
# Pattern4: 발사체
# ══════════════════════════════════════════════════
class Pattern4(Pattern):
    """12개 발사대를 원형 배치하고, 양옆 2칸 제외 후 랜덤 대상에 발사체를 날린다."""

    def __init__(self):
        super().__init__()
        self._emitters:   list[Emitter]    = []
        self._projectiles: list[Projectile] = []
        self._emit_timer:  float            = 1.2

        outer_r = 290
        for i in range(12):
            a = math.pi * 2 * i / 12
            self._emitters.append(
                Emitter(GCX + math.cos(a) * outer_r,
                        GCY + math.sin(a) * outer_r,
                        idx=i))

    def update(self, dt: float, player) -> None:
        self._emit_timer -= dt
        active_proj = [p for p in self._projectiles if p.active]
        n_em = len(self._emitters)
        if self._emit_timer <= 0 and len(active_proj) < 10 and n_em >= 6:
            self._emit_timer = random.uniform(0.20, 0.50)
            src = random.choice(self._emitters)
            excl = {src.idx,
                    (src.idx - 1) % n_em, (src.idx - 2) % n_em,
                    (src.idx + 1) % n_em, (src.idx + 2) % n_em}
            avail = [e for e in self._emitters if e.idx not in excl]
            if avail:
                tgt = random.choice(avail)
                dx = tgt.x - src.x
                dy = tgt.y - src.y
                d  = math.hypot(dx, dy) or 1
                self._projectiles.append(
                    Projectile(src.x, src.y,
                               dx / d * 390, dy / d * 390,
                               target=tgt))
        self._projectiles = Pattern._process_active(self._projectiles, dt, player)

    def draw(self, surface) -> None:
        for em in self._emitters:
            em.draw(surface)
        for pr in self._projectiles:
            pr.draw(surface)


# ══════════════════════════════════════════════════
# Pattern5: 벽 튕김 공
# ══════════════════════════════════════════════════
class Pattern5(Pattern):
    """14개의 BounceBall이 화면을 영구적으로 누빈다."""

    def __init__(self):
        super().__init__()
        self._balls: list[BounceBall] = []
        for _ in range(14):
            x   = random.uniform(80, SCREEN_W - 80)
            y   = random.uniform(80, SCREEN_H - 80)
            spd = random.uniform(100, 230)
            ang = random.uniform(0, math.pi * 2)
            self._balls.append(
                BounceBall(x, y, math.cos(ang) * spd, math.sin(ang) * spd))

    def update(self, dt: float, player) -> None:
        px, py = player.center
        for b in self._balls:
            b.update(dt)
            if b.collides(px, py):
                player.hit()

    def draw(self, surface) -> None:
        for b in self._balls:
            b.draw(surface)


# ══════════════════════════════════════════════════
# Stage 1  (다형성으로 Pattern 교체)
# ══════════════════════════════════════════════════
class Stage1:
    """6개 패턴을 시간 기준으로 순서대로 교체하며 진행되는 스테이지.

    다형성: _current는 Pattern 인터페이스만 사용하므로 구체 패턴 클래스를 몰라도 된다.
    캡슐화: P0→P1 전환(정리 대기) 로직이 Stage1 내부에만 존재한다.
    """
    _PATTERN_CLASSES = [Pattern0, Pattern1, Pattern2, Pattern3, Pattern4, Pattern5]

    def __init__(self, practice_p: Optional[int] = None):
        self.practice_p = practice_p
        start_idx       = practice_p if practice_p is not None else 0
        self._pattern_idx: int              = start_idx
        self._current:     Pattern          = self._PATTERN_CLASSES[start_idx]()
        self._clearing:    bool             = False
        self._old_p0:      Optional[Pattern0] = None

    # ── 시간 기준 목표 패턴 번호 ─────────────────
    def _desired(self, elapsed: float) -> int:
        if self.practice_p is not None:
            return self.practice_p
        for i, b in enumerate(P_BREAKS):
            if elapsed < b:
                return i
        return len(P_BREAKS) - 1

    # ── 메인 업데이트 (다형성 활용) ──────────────
    def update(self, dt: float, elapsed: float, player) -> None:
        desired = self._desired(elapsed)

        # P0→P1 전환 대기: 기존 P0 공이 모두 빠질 때까지
        if self._clearing and self._old_p0 is not None:
            self._old_p0.update(dt, player)
            if self._old_p0.is_empty:
                self._clearing   = False
                self._old_p0     = None
                self._pattern_idx = 1
                self._current    = Pattern1()
            return

        # 패턴 전환 감지
        if desired != self._pattern_idx:
            if self._pattern_idx == 0 and desired == 1:
                # P0 → P1: 정리 모드 진입
                p0 = self._current
                assert isinstance(p0, Pattern0)
                p0.is_clearing   = True
                self._old_p0     = p0
                self._clearing   = True
                return
            else:
                self._pattern_idx = desired
                self._current     = self._PATTERN_CLASSES[desired]()

        # 현재 패턴 업데이트 (다형성: Pattern 인터페이스)
        self._current.update(dt, player)

    # ── 그리기 (다형성 활용) ─────────────────────
    def draw(self, surface) -> None:
        if self._clearing and self._old_p0 is not None:
            self._old_p0.draw(surface)
            return
        # 다형성: 구체 패턴 클래스에 관계없이 동일한 draw() 호출
        self._current.draw(surface)


# ══════════════════════════════════════════════════
# 메뉴 아이템 정의
# ══════════════════════════════════════════════════
MENU_ITEMS = {
    (0, 0): ("GO", None),
    (1, 0): ("1",  0),
    (2, 0): ("2",  1),
    (3, 0): ("3",  2),
    (0, 1): ("4",  3),
    (1, 1): ("5",  4),
    (2, 1): ("6",  5),
}


async def run_menu():
    """타이틀 메뉴: 그리드에서 GO / 1~6 패턴 연습 선택."""
    font_big   = pygame.font.Font(None, 52)
    font_med   = pygame.font.Font(None, 40)
    font_small = pygame.font.Font(None, 26)

    cur_col, cur_row = 0, 0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                elif event.key in (pygame.K_LEFT,  pygame.K_a):
                    cur_col = (cur_col - 1) % COLS
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    cur_col = (cur_col + 1) % COLS
                elif event.key in (pygame.K_UP,    pygame.K_w):
                    cur_row = (cur_row - 1) % ROWS
                elif event.key in (pygame.K_DOWN,  pygame.K_s):
                    cur_row = (cur_row + 1) % ROWS
                elif event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    key = (cur_col, cur_row)
                    if key in MENU_ITEMS:
                        return MENU_ITEMS[key][1]

        screen.fill(BG)

        for row in range(ROWS):
            for col in range(COLS):
                cx = GRID_X + col * CELL + CELL // 2
                cy = GRID_Y + row * CELL + CELL // 2
                key = (col, row)
                is_cursor = (col == cur_col and row == cur_row)
                has_item  = key in MENU_ITEMS

                if is_cursor:
                    hi = pygame.Surface((CELL - 2, CELL - 2), pygame.SRCALPHA)
                    alpha = 40 if has_item else 16
                    hi.fill((255, 255, 255, alpha))
                    screen.blit(hi, (GRID_X + col * CELL + 1, GRID_Y + row * CELL + 1))

                if has_item:
                    label = MENU_ITEMS[key][0]
                    if label == "GO":
                        color = P_GREEN if not is_cursor else (160, 255, 160)
                    else:
                        color = TXT if not is_cursor else (220, 220, 220)
                    txt = font_med.render(label, True, color)
                    screen.blit(txt, txt.get_rect(center=(cx, cy)))

        draw_grid(screen)

        t1 = font_big.render("4x4  STAGE 1", True, TXT)
        screen.blit(t1, t1.get_rect(centerx=SCREEN_W // 2, top=96))

        cur_key = (cur_col, cur_row)
        if cur_key in MENU_ITEMS:
            label = MENU_ITEMS[cur_key][0]
            hint = "정상 게임 시작" if label == "GO" else f"패턴 {label}  무한 연습 모드"
        else:
            hint = "빈 칸"
        t2 = font_small.render(hint, True, (160, 160, 160))
        screen.blit(t2, t2.get_rect(centerx=SCREEN_W // 2,
                                     top=GRID_Y + GRID_PX + 22))

        t3 = font_small.render(
            "<- ->  이동     Space / Enter  선택     ESC  종료",
            True, (60, 60, 60))
        screen.blit(t3, t3.get_rect(centerx=SCREEN_W // 2, bottom=SCREEN_H - 14))

        pygame.display.flip()
        clock.tick(60)
        await asyncio.sleep(0)


# ══════════════════════════════════════════════════
# 메인 루프
# ══════════════════════════════════════════════════
async def run_stage1(practice_pattern: Optional[int] = None):
    font_big   = pygame.font.Font(None, 44)
    font_small = pygame.font.Font(None, 28)

    player  = Player()
    stage   = Stage1(practice_p=practice_pattern)
    elapsed = 0.0
    state   = "play"

    while True:
        dt = min(clock.tick(60) / 1000.0, 0.05)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if practice_pattern is not None:
                        return
                    pygame.quit(); sys.exit()
                if state != "play":
                    if event.key == pygame.K_r:
                        await run_stage1(practice_pattern=practice_pattern); return
                else:
                    if   event.key in (pygame.K_LEFT,  pygame.K_a): player.move(-1,  0)
                    elif event.key in (pygame.K_RIGHT, pygame.K_d): player.move( 1,  0)
                    elif event.key in (pygame.K_UP,    pygame.K_w): player.move( 0, -1)
                    elif event.key in (pygame.K_DOWN,  pygame.K_s): player.move( 0,  1)

        if state == "play":
            player.update(dt)
            stage.update(dt, elapsed, player)

            if player.lives <= 0:
                if practice_pattern is not None:
                    player.lives = 3
                    player.inv   = 0.0
                else:
                    state = "dead"

            if practice_pattern is None:
                elapsed += dt
                if elapsed >= TOTAL:
                    state = "clear"

        screen.fill(BG)
        draw_grid(screen)
        stage.draw(screen)
        if state != "dead":
            player.draw(screen)

        if practice_pattern is not None:
            ptxt = font_big.render(f"PRACTICE  P{practice_pattern + 1}", True, TXT)
        else:
            pct  = min(elapsed / TOTAL * 100, 100)
            ptxt = font_big.render(f"{pct:.2f}%", True, TXT)
        screen.blit(ptxt, ptxt.get_rect(centerx=SCREEN_W // 2, top=14))

        life_colors = [P_BLUE, P_GREEN, P_RED]
        for i in range(3):
            cx = SCREEN_W - 30 - i * 30
            cy = 26
            if i < player.lives:
                pygame.draw.circle(screen, life_colors[i], (cx, cy), 10)
            else:
                pygame.draw.circle(screen, (38, 38, 38), (cx, cy), 10)
                pygame.draw.circle(screen, (62, 62, 62), (cx, cy), 10, 1)

        if state == "dead":
            ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 148))
            screen.blit(ov, (0, 0))
            t1 = font_big.render("GAME OVER", True, P_RED)
            t2 = font_small.render("R : 재시작    ESC : 종료", True, TXT)
            screen.blit(t1, t1.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 - 26)))
            screen.blit(t2, t2.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 + 18)))

        elif state == "clear":
            ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 148))
            screen.blit(ov, (0, 0))
            t1 = font_big.render("STAGE CLEAR!", True, P_GREEN)
            t2 = font_small.render("R : 다시하기    ESC : 종료", True, TXT)
            screen.blit(t1, t1.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 - 26)))
            screen.blit(t2, t2.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 + 18)))

        pygame.display.flip()
        await asyncio.sleep(0)


async def main():
    if sys.platform == "emscripten":
        await run_stage1(practice_pattern=None)
        return

    while True:
        choice = await run_menu()
        await run_stage1(practice_pattern=choice)


async def show_startup_error(exc: BaseException):
    font = pygame.font.Font(None, 28)
    lines = ["WEB STARTUP ERROR", *traceback.format_exception(exc)]
    while True:
        screen.fill((18, 0, 0))
        y = 24
        for raw in lines[:22]:
            for line in raw.rstrip().splitlines() or [""]:
                text = font.render(line[:110], True, (255, 210, 210))
                screen.blit(text, (24, y))
                y += 28
                if y > SCREEN_H - 30:
                    break
            if y > SCREEN_H - 30:
                break
        pygame.display.flip()
        await asyncio.sleep(0.1)


async def safe_main():
    try:
        await main()
    except BaseException as exc:
        await show_startup_error(exc)


asyncio.run(safe_main())

