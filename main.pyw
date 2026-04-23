"""
Minecraft-like 2D Game using Pygame
Features: block breaking/placing, pig combat with HP bars,
dropped block items, full inventory screen (I key), crafting, survival mechanics,
title screen with settings, developer console (F9), crash report logging.
"""

import pygame
import sys
import os
import math
import random
import traceback
import datetime
from enum import Enum

# ============================================================================
# PATH HELPERS  (everything relative to the script's own directory)
# ============================================================================

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR  = os.path.join(BASE_DIR, "logs")
TITLE_IMG = os.path.join(BASE_DIR, "title.png")

def ensure_logs_dir():
    os.makedirs(LOGS_DIR, exist_ok=True)

# ============================================================================
# DEVELOPER LOGGER
# ============================================================================

class DevLogger:
    """
    Singleton logger.
    • Always prints to stdout (developer terminal output).
    • Keeps the last MAX_LINES messages in memory for the F9 console window.
    • Levels: INFO, WARN, ERROR, DEBUG
    """
    MAX_LINES = 200
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._lines = []          # list of (level, message)
            cls._instance._scroll = 0
        return cls._instance

    def _log(self, level, msg):
        ts   = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] [{level}] {msg}"
        print(line)                            # always to stdout / terminal
        self._lines.append((level, line))
        if len(self._lines) > self.MAX_LINES:
            self._lines.pop(0)

    def info (self, msg): self._log("INFO",  msg)
    def warn (self, msg): self._log("WARN",  msg)
    def error(self, msg): self._log("ERROR", msg)
    def debug(self, msg): self._log("DEBUG", msg)

    def scroll_up  (self, n=3): self._scroll = max(0, self._scroll - n)
    def scroll_down(self, n=3): self._scroll = min(max(0, len(self._lines) - 1), self._scroll + n)

    def draw(self, surface):
        """Draw the in-game developer console overlay."""
        W, H = surface.get_size()
        cw, ch = W - 40, H - 40
        cx, cy = 20, 20

        bg = pygame.Surface((cw, ch), pygame.SRCALPHA)
        bg.fill((10, 10, 10, 220))
        surface.blit(bg, (cx, cy))
        pygame.draw.rect(surface, (80, 200, 80), (cx, cy, cw, ch), 2)

        font  = pygame.font.Font(None, 18)
        title = pygame.font.Font(None, 22).render(
            "Developer Console  (F9 to close | ↑↓ or scroll to navigate)", True, (80, 255, 80))
        surface.blit(title, (cx + 8, cy + 6))

        line_h   = 16
        max_rows = (ch - 30) // line_h
        visible  = self._lines[self._scroll: self._scroll + max_rows]

        COLORS = {"INFO": (200,200,200), "WARN": (255,220,50),
                  "ERROR": (255,80,80),  "DEBUG": (100,200,255)}

        for i, (level, text) in enumerate(visible):
            color = COLORS.get(level, (200,200,200))
            surf  = font.render(text, True, color)
            surface.blit(surf, (cx + 8, cy + 26 + i * line_h))

        # scrollbar
        if len(self._lines) > max_rows:
            sb_h   = ch - 30
            thumb_h = max(20, sb_h * max_rows // len(self._lines))
            thumb_y = cy + 26 + (sb_h - thumb_h) * self._scroll // max(1, len(self._lines) - max_rows)
            pygame.draw.rect(surface, (60,60,60), (cx + cw - 10, cy + 26, 8, sb_h))
            pygame.draw.rect(surface, (80,200,80),(cx + cw - 10, thumb_y, 8, thumb_h))

log = DevLogger()   # global singleton

# ============================================================================
# CRASH REPORT
# ============================================================================

def save_crash_report(exc_info):
    ensure_logs_dir()
    ts       = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(LOGS_DIR, f"crash_{ts}.txt")
    with open(filename, "w") as f:
        f.write(f"Crash Report — {datetime.datetime.now()}\n")
        f.write("=" * 60 + "\n")
        f.write(traceback.format_exc())
    log.error(f"Crash report saved → {filename}")
    return filename

# ============================================================================
# SETTINGS  (volume, key-mapping, crash-report toggle)
# ============================================================================

DEFAULT_KEYS = {
    "move_left":  pygame.K_a,
    "move_right": pygame.K_d,
    "jump":       pygame.K_SPACE,
    "eat":        pygame.K_e,
    "inventory":  pygame.K_i,
    "craft":      pygame.K_c,
}

class Settings:
    def __init__(self):
        self.volume           = 0.5          # 0.0 – 1.0
        self.keys             = dict(DEFAULT_KEYS)
        self.save_crash_report = True

settings = Settings()

# ============================================================================
# CONSTANTS
# ============================================================================

WINDOW_WIDTH  = 1200
WINDOW_HEIGHT = 800
BLOCK_SIZE    = 48
WORLD_WIDTH   = 100
WORLD_HEIGHT  = 100
FPS           = 60

GRAVITY               = 0.6
FALL_DAMAGE_THRESHOLD = 3
MAX_HEALTH            = 20
MAX_HUNGER            = 20
PICKUP_RADIUS         = BLOCK_SIZE * 1.5


class BlockType(Enum):
    GRASS  = (34,  139,  34)
    DIRT   = (139,  69,  19)
    STONE  = (128, 128, 128)
    WATER  = ( 30, 144, 255)
    SAND   = (238, 214, 175)
    WOOD   = (101,  67,  33)
    LEAVES = ( 34, 200,  34)

BLOCK_COLORS = {bt: bt.value for bt in BlockType}

class ItemType(Enum):
    BACON = "BACON"

class ToolType(Enum):
    SHOVEL  = "SHOVEL"
    PICKAXE = "PICKAXE"
    AXE     = "AXE"
    HOE     = "HOE"
    SWORD   = "SWORD"

BLOCK_BREAK_TIMES = {
    BlockType.GRASS: 50,  BlockType.DIRT: 50,  BlockType.STONE: 200,
    BlockType.SAND:  40,  BlockType.WATER: 10,  BlockType.WOOD:  100,
    BlockType.LEAVES: 30,
}

TOOL_EFFECTIVENESS = {
    ToolType.SHOVEL:  {BlockType.DIRT: 0.5,  BlockType.SAND:   0.5},
    ToolType.PICKAXE: {BlockType.STONE: 0.3},
    ToolType.AXE:     {BlockType.WOOD:  0.3,  BlockType.LEAVES: 0.3},
    ToolType.HOE:     {BlockType.GRASS: 0.5,  BlockType.DIRT:   0.5},
    ToolType.SWORD:   {},
}

CRAFTING_RECIPES = {
    ToolType.SHOVEL:  {BlockType.WOOD: 5,  ItemType.BACON:  1},
    ToolType.PICKAXE: {BlockType.STONE: 3, BlockType.WOOD:  4},
    ToolType.AXE:     {BlockType.WOOD:  6, BlockType.STONE: 2},
    ToolType.HOE:     {BlockType.DIRT:  3, BlockType.WOOD:  3},
    ToolType.SWORD:   {BlockType.STONE: 2, BlockType.WOOD:  3},
}

# ============================================================================
# TITLE / SETTINGS SCREEN
# ============================================================================

class TitleScreen:
    """
    Displays:
      • Logo image (title.png) centred near top
      • Play / Settings / Quit buttons
      • Settings sub-screen with volume slider, key-mapping, crash-report toggle
    Returns "play" or "quit" from run().
    """

    BTN_W, BTN_H = 260, 54
    ACCENT = (80, 200, 80)
    BG     = (15, 20, 15)

    def __init__(self, screen, clock):
        self.screen = screen
        self.clock  = clock
        self.font_big   = pygame.font.Font(None, 64)
        self.font_med   = pygame.font.Font(None, 36)
        self.font_small = pygame.font.Font(None, 24)

        # Try to load logo
        self.logo = None
        if os.path.exists(TITLE_IMG):
            try:
                raw = pygame.image.load(TITLE_IMG).convert_alpha()
                max_w, max_h = WINDOW_WIDTH - 100, 220
                ratio = min(max_w / raw.get_width(), max_h / raw.get_height())
                new_w = int(raw.get_width()  * ratio)
                new_h = int(raw.get_height() * ratio)
                self.logo = pygame.transform.smoothscale(raw, (new_w, new_h))
                log.info(f"Title logo loaded from {TITLE_IMG}")
            except Exception as e:
                log.warn(f"Could not load title.png: {e}")
        else:
            log.warn(f"title.png not found at {TITLE_IMG}; using text fallback")

        self.state        = "main"    # "main" | "settings" | "keybind"
        self.keybind_action = None    # which action is waiting for a key press

        # Volume drag state
        self._dragging_vol = False

    # ── helpers ──────────────────────────────────────────────────────────────

    def _btn_rect(self, cx, cy):
        return pygame.Rect(cx - self.BTN_W//2, cy - self.BTN_H//2, self.BTN_W, self.BTN_H)

    def _draw_button(self, label, cx, cy, hovered=False):
        r  = self._btn_rect(cx, cy)
        bg = (30, 60, 30) if hovered else (20, 40, 20)
        pygame.draw.rect(self.screen, bg, r, border_radius=8)
        pygame.draw.rect(self.screen, self.ACCENT, r, 2, border_radius=8)
        txt = self.font_med.render(label, True, (230,255,230) if hovered else (180,220,180))
        self.screen.blit(txt, txt.get_rect(center=r.center))
        return r

    def _draw_header(self, title):
        self.screen.fill(self.BG)
        # logo or text
        if self.logo:
            lx = WINDOW_WIDTH  // 2 - self.logo.get_width()  // 2
            ly = 30
            self.screen.blit(self.logo, (lx, ly))
            y_after_logo = ly + self.logo.get_height() + 20
        else:
            t = self.font_big.render("Minecraft 2D", True, self.ACCENT)
            self.screen.blit(t, t.get_rect(center=(WINDOW_WIDTH//2, 100)))
            y_after_logo = 160
        if title:
            sub = self.font_med.render(title, True, (140,200,140))
            self.screen.blit(sub, sub.get_rect(center=(WINDOW_WIDTH//2, y_after_logo)))
        return y_after_logo + 40

    # ── main menu ────────────────────────────────────────────────────────────

    def _draw_main(self, mouse):
        cy = self._draw_header("")
        cy = max(cy, WINDOW_HEIGHT // 2 - 60)
        btns = {}
        for label in ("Play", "Settings", "Quit"):
            btns[label] = self._draw_button(label, WINDOW_WIDTH//2, cy,
                                             hovered=self._btn_rect(WINDOW_WIDTH//2, cy).collidepoint(mouse))
            cy += self.BTN_H + 20
        hint = self.font_small.render("Press F9 during gameplay to open the developer console", True, (80,120,80))
        self.screen.blit(hint, hint.get_rect(center=(WINDOW_WIDTH//2, WINDOW_HEIGHT - 30)))
        return btns

    def _handle_main(self, event, btns):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if btns["Play"].collidepoint(event.pos):
                log.info("Player pressed Play")
                return "play"
            if btns["Settings"].collidepoint(event.pos):
                log.info("Entering settings screen")
                self.state = "settings"
            if btns["Quit"].collidepoint(event.pos):
                log.info("Player quit from title screen")
                return "quit"
        return None

    # ── settings screen ──────────────────────────────────────────────────────

    def _draw_settings(self, mouse):
        top = self._draw_header("Settings")
        x0  = WINDOW_WIDTH // 2
        tc  = (220, 255, 220)
        y   = top

        # ── Volume slider ──
        self.screen.blit(self.font_med.render("Volume", True, tc), (x0 - 220, y))
        vol_rect = pygame.Rect(x0 - 20, y + 8, 200, 20)
        pygame.draw.rect(self.screen, (50,80,50),   vol_rect, border_radius=5)
        fill_w = int(vol_rect.width * settings.volume)
        pygame.draw.rect(self.screen, self.ACCENT,
                         (vol_rect.x, vol_rect.y, fill_w, vol_rect.height), border_radius=5)
        pygame.draw.rect(self.screen, (180,220,180), vol_rect, 2, border_radius=5)
        # thumb
        thumb_x = vol_rect.x + fill_w
        pygame.draw.circle(self.screen, (255,255,255), (thumb_x, vol_rect.centery), 10)
        pct = self.font_small.render(f"{int(settings.volume*100)}%", True, tc)
        self.screen.blit(pct, (vol_rect.right + 12, y + 4))

        # drag logic
        if self._dragging_vol:
            rel = (mouse[0] - vol_rect.x) / vol_rect.width
            settings.volume = max(0.0, min(1.0, rel))
            pygame.mixer.music.set_volume(settings.volume)

        y += 60

        # ── Key bindings ──
        self.screen.blit(self.font_med.render("Key Bindings", True, tc), (x0 - 220, y))
        y += 36
        self._keybind_rects = {}
        for action, key in settings.keys.items():
            label = action.replace("_", " ").title()
            key_name = pygame.key.name(key).upper()
            lsurf = self.font_small.render(f"{label}:", True, (180,220,180))
            self.screen.blit(lsurf, (x0 - 220, y + 4))

            waiting = (self.keybind_action == action)
            btn_txt = "[ press a key… ]" if waiting else f"[ {key_name} ]"
            btn_col = (255,220,50) if waiting else (180,220,180)
            btn_rect = pygame.Rect(x0 + 20, y, 160, 30)
            pygame.draw.rect(self.screen, (40,60,40) if not waiting else (60,50,10), btn_rect, border_radius=4)
            pygame.draw.rect(self.screen, btn_col, btn_rect, 1, border_radius=4)
            bsurf = self.font_small.render(btn_txt, True, btn_col)
            self.screen.blit(bsurf, bsurf.get_rect(center=btn_rect.center))
            self._keybind_rects[action] = btn_rect
            y += 36

        y += 10

        # ── Crash report toggle ──
        self.screen.blit(self.font_med.render("Save Crash Reports", True, tc), (x0 - 220, y))
        tog_rect = pygame.Rect(x0 + 20, y + 2, 80, 30)
        tog_col  = (50,200,50) if settings.save_crash_report else (150,50,50)
        pygame.draw.rect(self.screen, tog_col, tog_rect, border_radius=6)
        pygame.draw.rect(self.screen, (220,220,220), tog_rect, 2, border_radius=6)
        tog_txt = self.font_small.render("ON" if settings.save_crash_report else "OFF", True, (255,255,255))
        self.screen.blit(tog_txt, tog_txt.get_rect(center=tog_rect.center))
        y += 50

        # ── Back button ──
        back_rect = self._draw_button("Back", x0 - 80, y + 30,
                                       hovered=self._btn_rect(x0 - 80, y + 30).collidepoint(mouse))

        return vol_rect, tog_rect, back_rect

    def _handle_settings(self, event, vol_rect, tog_rect, back_rect):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # volume drag start
            thumb_x = vol_rect.x + int(vol_rect.width * settings.volume)
            if abs(event.pos[0] - thumb_x) <= 12 and abs(event.pos[1] - vol_rect.centery) <= 12:
                self._dragging_vol = True
            # crash toggle
            if tog_rect.collidepoint(event.pos):
                settings.save_crash_report = not settings.save_crash_report
                log.info(f"Crash report saving: {settings.save_crash_report}")
            # keybind buttons
            for action, rect in self._keybind_rects.items():
                if rect.collidepoint(event.pos):
                    self.keybind_action = action
                    log.debug(f"Waiting for new key for action '{action}'")
            # back
            if back_rect.collidepoint(event.pos):
                self.state = "main"
                self.keybind_action = None

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._dragging_vol = False

        # keybind capture
        if event.type == pygame.KEYDOWN and self.keybind_action:
            if event.key != pygame.K_ESCAPE:
                settings.keys[self.keybind_action] = event.key
                log.info(f"Key '{self.keybind_action}' rebound to {pygame.key.name(event.key)}")
            self.keybind_action = None

    # ── main run loop ─────────────────────────────────────────────────────────

    def run(self):
        log.info("Title screen started")
        while True:
            mouse = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit()

                if self.state == "main":
                    btns   = self._draw_main(mouse)
                    result = self._handle_main(event, btns)
                    if result:
                        return result
                elif self.state == "settings":
                    vr, tr, br = self._draw_settings(mouse)
                    self._handle_settings(event, vr, tr, br)

            # draw (needs to happen every frame even without events for drag)
            if self.state == "main":
                self._draw_main(mouse)
            elif self.state == "settings":
                self._draw_settings(mouse)

            pygame.display.flip()
            self.clock.tick(60)

# ============================================================================
# DROPPED ITEM
# ============================================================================

class DroppedItem:
    SIZE = 16

    def __init__(self, world_x, world_y, item_type):
        self.x         = world_x * BLOCK_SIZE + BLOCK_SIZE // 2
        self.y         = world_y * BLOCK_SIZE + BLOCK_SIZE // 2
        self.item_type = item_type
        self.age       = 0
        self.color     = (BLOCK_COLORS[item_type]
                          if isinstance(item_type, BlockType) else (255, 180, 50))

    def update(self): self.age += 1

    def draw(self, surface, camera_x, camera_y):
        sx   = int(self.x - camera_x)
        sy   = int(self.y - camera_y - 4 * math.sin(self.age * 0.08))
        half = self.SIZE // 2
        pygame.draw.rect(surface, self.color,   (sx-half, sy-half, self.SIZE, self.SIZE))
        pygame.draw.rect(surface, (255,255,255), (sx-half, sy-half, self.SIZE, self.SIZE), 1)

# ============================================================================
# BLOCK
# ============================================================================

class Block:
    def __init__(self, block_type=BlockType.GRASS):
        self.block_type = block_type
        self.color      = BLOCK_COLORS[block_type]

    def draw(self, surface, x, y, size):
        pygame.draw.rect(surface, self.color, (x, y, size, size))
        pygame.draw.rect(surface, (0,0,0),    (x, y, size, size), 1)

# ============================================================================
# WORLD
# ============================================================================

class World:
    def __init__(self, width, height):
        self.width  = width
        self.height = height
        self.blocks = {}
        log.info("Generating world…")
        self._generate_world()
        log.info(f"World generated — {len(self.blocks)} blocks placed")

    def _generate_world(self):
        hm = self._generate_height_map()
        for x in range(self.width):
            sh = hm[x]
            for y in range(self.height):
                if y < sh:   continue
                elif y == sh:                   self.blocks[(x,y)] = Block(BlockType.GRASS)
                elif y < sh+3:                  self.blocks[(x,y)] = Block(BlockType.DIRT)
                elif y < sh+15:
                    bt = BlockType.STONE if random.random()<0.8 else BlockType.DIRT
                    self.blocks[(x,y)] = Block(bt)
                else:
                    bt = BlockType.STONE if random.random()<0.9 else BlockType.SAND
                    self.blocks[(x,y)] = Block(bt)
        self._generate_water(hm)
        self._generate_trees(hm)
        self._generate_decorations(hm)

    def _generate_height_map(self):
        hm = []
        for x in range(self.width):
            h = 40 if x==0 else max(25, min(55, hm[x-1]+random.randint(-1,1)))
            hm.append(h)
        return hm

    def _generate_water(self, hm):
        for x in range(self.width//4, self.width//3):
            ws = hm[x]+1
            for y in range(ws, ws+5):
                if y < self.height: self.blocks[(x,y)] = Block(BlockType.WATER)

    def _generate_trees(self, hm):
        count = 0
        for x in range(self.width):
            if random.random()<0.08:
                sh=hm[x]; th=random.randint(4,7); ty=sh-1
                for i in range(th):
                    if ty-i>=0: self.blocks[(x,ty-i)]=Block(BlockType.WOOD)
                ly=ty-th; lr=3
                for dx in range(-lr,lr+1):
                    for dy in range(-lr,lr+1):
                        lx2,ly2=x+dx,ly+dy
                        if (dx**2+(dy-1)**2)**0.5<=lr and 0<=lx2<self.width and 0<=ly2<self.height:
                            if not(lx2==x and ly-lr<=ly2<=ly):
                                if (lx2,ly2) not in self.blocks:
                                    self.blocks[(lx2,ly2)]=Block(BlockType.LEAVES)
                count+=1
        log.debug(f"Trees generated: {count}")

    def _generate_decorations(self, hm):
        for x in range(self.width):
            if random.random()<0.05:
                sh=hm[x]
                for dy in range(3):
                    sy=sh+dy
                    if (x,sy) in self.blocks and self.blocks[(x,sy)].block_type==BlockType.DIRT:
                        self.blocks[(x,sy)]=Block(BlockType.SAND)

    def get_block(self,x,y):   return self.blocks.get((x,y))
    def is_solid(self,x,y):    return (x,y) in self.blocks

    def place_block(self,x,y,bt):
        if 0<=x<self.width and 0<=y<self.height:
            self.blocks[(x,y)]=Block(bt); return True
        return False

    def remove_block(self,x,y):
        if (x,y) in self.blocks:
            del self.blocks[(x,y)]; return True
        return False

    def draw(self, surface, camera_x, camera_y):
        sx0=max(0, camera_x//BLOCK_SIZE); sy0=max(0, camera_y//BLOCK_SIZE)
        sx1=min(self.width,  (camera_x+WINDOW_WIDTH) //BLOCK_SIZE+1)
        sy1=min(self.height, (camera_y+WINDOW_HEIGHT)//BLOCK_SIZE+1)
        for x in range(sx0,sx1):
            for y in range(sy0,sy1):
                b=self.get_block(x,y)
                if b: b.draw(surface, x*BLOCK_SIZE-camera_x, y*BLOCK_SIZE-camera_y, BLOCK_SIZE)

# ============================================================================
# PLAYER
# ============================================================================

class Player:
    def __init__(self, x, y):
        self.x=x*BLOCK_SIZE+BLOCK_SIZE//2; self.y=y*BLOCK_SIZE+BLOCK_SIZE//2
        self.width=BLOCK_SIZE*0.7; self.height=BLOCK_SIZE*0.95
        self.speed=4; self.color=(255,100,100)
        self.velocity_y=0; self.is_on_ground=False; self.fall_distance=0
        self.health=MAX_HEALTH; self.hunger=MAX_HUNGER
        self.hunger_drain_counter=0; self.hunger_drain_rate=120
        self.health_drain_counter=0; self.health_drain_rate=30
        self.hotbar_size=9; self.hotbar=[None]*9; self.selected_hotbar_slot=0
        self.inventory={}; self.breaking_block=None; self.break_progress=0
        self.tools={}; self.selected_tool=None
        log.info("Player initialised")

    def get_grid_pos(self): return (int(self.x//BLOCK_SIZE), int(self.y//BLOCK_SIZE))
    def get_selected_item(self): return self.hotbar[self.selected_hotbar_slot]

    def update(self, keys, world):
        dx=0
        if keys[settings.keys["move_left"]]:  dx=-self.speed
        if keys[settings.keys["move_right"]]: dx= self.speed
        self.velocity_y=min(self.velocity_y+GRAVITY,15)
        self.is_on_ground=self._check_ground(world)
        if keys[settings.keys["jump"]] and self.is_on_ground:
            self.velocity_y=-12; self.is_on_ground=False
        new_x=self.x+dx
        if self._can_move_to(new_x,self.y,world): self.x=new_x
        new_y=self.y+self.velocity_y
        if self.velocity_y>0:  self.fall_distance+=self.velocity_y
        elif self.velocity_y<0: self.fall_distance=0
        if self._can_move_to(self.x,new_y,world):
            self.y=new_y
        else:
            if self.velocity_y>0:
                if self.fall_distance>FALL_DAMAGE_THRESHOLD*BLOCK_SIZE:
                    dmg=int((self.fall_distance-FALL_DAMAGE_THRESHOLD*BLOCK_SIZE)/BLOCK_SIZE)
                    self.take_damage(dmg)
                    log.warn(f"Player took {dmg} fall damage")
                self.fall_distance=0
            self.velocity_y=0
        self.hunger_drain_counter+=1
        if self.hunger_drain_counter>=self.hunger_drain_rate:
            self.hunger=max(0,self.hunger-1); self.hunger_drain_counter=0
        if self.hunger<=0:
            self.health_drain_counter+=1
            if self.health_drain_counter>=self.health_drain_rate:
                self.take_damage(1); self.health_drain_counter=0

    def _check_ground(self,world):
        hw=self.width/2
        for gx,gy in [(int((self.x-hw)//BLOCK_SIZE),int((self.y+self.height/2+3)//BLOCK_SIZE)),
                       (int((self.x+hw)//BLOCK_SIZE),int((self.y+self.height/2+3)//BLOCK_SIZE))]:
            if world.is_solid(gx,gy): return True
        return False

    def _can_move_to(self,x,y,world):
        hw,hh=self.width/2,self.height/2
        for gx,gy in [(int((x-hw)//BLOCK_SIZE),int((y-hh)//BLOCK_SIZE)),
                       (int((x+hw)//BLOCK_SIZE),int((y-hh)//BLOCK_SIZE)),
                       (int((x-hw)//BLOCK_SIZE),int((y+hh)//BLOCK_SIZE)),
                       (int((x+hw)//BLOCK_SIZE),int((y+hh)//BLOCK_SIZE))]:
            if world.is_solid(gx,gy): return False
        if x-hw<0 or x+hw>world.width*BLOCK_SIZE:   return False
        if y-hh<0 or y+hh>world.height*BLOCK_SIZE:  return False
        return True

    def add_to_inventory(self,item_type,count=1):
        self.inventory[item_type]=self.inventory.get(item_type,0)+count
        log.debug(f"Picked up {count}x {item_type.name}  (total: {self.inventory[item_type]})")
        if isinstance(item_type,BlockType):
            for i,slot in enumerate(self.hotbar):
                if slot and slot[0]==item_type:
                    self.hotbar[i]=(item_type,slot[1]+count); return
            for i,slot in enumerate(self.hotbar):
                if slot is None:
                    self.hotbar[i]=(item_type,count); return

    def get_inventory_count(self,it): return self.inventory.get(it,0)

    def remove_from_inventory(self,it,count=1):
        if it in self.inventory:
            self.inventory[it]=max(0,self.inventory[it]-count)

    def craft_item(self,tool_type):
        if tool_type not in CRAFTING_RECIPES: return False
        recipe=CRAFTING_RECIPES[tool_type]
        for it,n in recipe.items():
            if self.get_inventory_count(it)<n: return False
        for it,n in recipe.items(): self.remove_from_inventory(it,n)
        self.tools[tool_type]=self.tools.get(tool_type,0)+1
        log.info(f"Crafted {tool_type.name}")
        return True

    def select_hotbar_slot(self,slot):
        if 0<=slot<self.hotbar_size: self.selected_hotbar_slot=slot

    def get_tool_efficiency(self,bt):
        if self.selected_tool is None or self.selected_tool not in TOOL_EFFECTIVENESS: return 1.0
        return TOOL_EFFECTIVENESS[self.selected_tool].get(bt,1.0)

    def eat_bacon(self):
        if self.get_inventory_count(ItemType.BACON)>0:
            self.remove_from_inventory(ItemType.BACON,1)
            self.hunger=min(MAX_HUNGER,self.hunger+4)
            log.info("Player ate bacon (+4 hunger)")
            return True
        log.debug("Tried to eat bacon but none in inventory")
        return False

    def take_damage(self,d):
        self.health=max(0,self.health-d)
        log.debug(f"Player health: {self.health}/{MAX_HEALTH}")

    def is_alive(self): return self.health>0

    def draw(self,surface,camera_x,camera_y):
        sx,sy=self.x-camera_x,self.y-camera_y
        bw,bh=self.width*0.6,self.height*0.6
        pygame.draw.rect(surface,self.color,(sx-bw/2,sy-bh/2+5,bw,bh))
        hr=int(self.width*0.35)
        pygame.draw.circle(surface,(255,180,100),(int(sx),int(sy-bh/2-hr)),hr)
        ey=sy-bh/2-hr+5
        pygame.draw.circle(surface,(0,0,0),(int(sx-5),int(ey)),2)
        pygame.draw.circle(surface,(0,0,0),(int(sx+5),int(ey)),2)
        ay=sy-bh/2+10
        pygame.draw.line(surface,self.color,(sx-bw/2-5,ay),(sx-bw/2-15,ay),4)
        pygame.draw.line(surface,self.color,(sx+bw/2+5,ay),(sx+bw/2+15,ay),4)
        pygame.draw.rect(surface,(0,0,0),(sx-bw/2,sy-bh/2+5,bw,bh),2)

# ============================================================================
# PIG
# ============================================================================

class Pig:
    MAX_HEALTH=5

    def __init__(self,x,y):
        self.x=x*BLOCK_SIZE+BLOCK_SIZE//2; self.y=y*BLOCK_SIZE+BLOCK_SIZE//2
        self.width=BLOCK_SIZE*0.8; self.height=BLOCK_SIZE*0.6
        self.color=(255,150,150); self.velocity_y=0; self.speed=2
        self.is_on_ground=False; self.direction=random.choice([-1,1])
        self.wander_timer=0; self.wander_change_interval=random.randint(60,180)
        self.health=self.MAX_HEALTH; self.hit_cooldown=0; self.hp_bar_timer=0

    def _check_ground(self,world):
        hw=self.width/2
        for gx,gy in [(int((self.x-hw)//BLOCK_SIZE),int((self.y+self.height/2+3)//BLOCK_SIZE)),
                       (int((self.x+hw)//BLOCK_SIZE),int((self.y+self.height/2+3)//BLOCK_SIZE))]:
            if world.is_solid(gx,gy): return True
        return False

    def _can_move_to(self,x,y,world):
        hw,hh=self.width/2,self.height/2
        for gx,gy in [(int((x-hw)//BLOCK_SIZE),int((y-hh)//BLOCK_SIZE)),
                       (int((x+hw)//BLOCK_SIZE),int((y-hh)//BLOCK_SIZE)),
                       (int((x-hw)//BLOCK_SIZE),int((y+hh)//BLOCK_SIZE)),
                       (int((x+hw)//BLOCK_SIZE),int((y+hh)//BLOCK_SIZE))]:
            if world.is_solid(gx,gy): return False
        if x-hw<0 or x+hw>WORLD_WIDTH*BLOCK_SIZE:   return False
        if y-hh<0 or y+hh>WORLD_HEIGHT*BLOCK_SIZE:  return False
        return True

    def take_damage(self,damage):
        if self.hit_cooldown<=0:
            self.health-=damage; self.hit_cooldown=20; self.hp_bar_timer=180
            log.debug(f"Pig hit — HP {self.health}/{self.MAX_HEALTH}")

    def is_alive(self): return self.health>0

    def update(self,world):
        self.hit_cooldown-=1
        if self.hp_bar_timer>0: self.hp_bar_timer-=1
        self.velocity_y=min(self.velocity_y+GRAVITY,15)
        self.is_on_ground=self._check_ground(world)
        self.wander_timer+=1
        if self.wander_timer>=self.wander_change_interval:
            self.direction=random.choice([-1,1]); self.wander_timer=0
            self.wander_change_interval=random.randint(60,180)
        new_x=self.x+self.direction*self.speed
        if self._can_move_to(new_x,self.y,world): self.x=new_x
        else: self.direction*=-1
        new_y=self.y+self.velocity_y
        if self._can_move_to(self.x,new_y,world): self.y=new_y
        else: self.velocity_y=0

    def draw(self,surface,camera_x,camera_y):
        sx,sy=self.x-camera_x,self.y-camera_y
        bw,bh=self.width*0.7,self.height*0.7
        pygame.draw.rect(surface,self.color,(sx-bw/2,sy-bh/2,bw,bh))
        hr=int(self.width*0.25)
        pygame.draw.circle(surface,self.color,(int(sx+bw/3),int(sy-bh/2)),hr)
        sr=int(self.width*0.12)
        pygame.draw.circle(surface,(255,180,180),(int(sx+bw/2),int(sy-bh/3)),sr)
        pygame.draw.circle(surface,(0,0,0),(int(sx+bw/3-3),int(sy-bh/2-2)),2)
        pygame.draw.circle(surface,(0,0,0),(int(sx+bw/3+3),int(sy-bh/2-2)),2)
        pygame.draw.rect(surface,(0,0,0),(sx-bw/2,sy-bh/2,bw,bh),2)
        # HP bar
        if self.hp_bar_timer>0:
            bar_w=int(bw)+10; bar_h=6
            bx=int(sx-bar_w/2); by=int(sy-bh/2-hr*2-10)
            pct=self.health/self.MAX_HEALTH
            pygame.draw.rect(surface,(80,0,0),(bx,by,bar_w,bar_h))
            pygame.draw.rect(surface,(int(255*(1-pct)),int(255*pct),0),(bx,by,int(bar_w*pct),bar_h))
            pygame.draw.rect(surface,(255,255,255),(bx,by,bar_w,bar_h),1)
            ft=pygame.font.Font(None,16).render(f"{self.health}/{self.MAX_HEALTH}",True,(255,255,255))
            surface.blit(ft,(bx,by-12))

# ============================================================================
# CAMERA
# ============================================================================

class Camera:
    def __init__(self): self.x=self.y=0

    def update(self,player):
        self.x=max(0,min(player.x-WINDOW_WIDTH//2,  WORLD_WIDTH *BLOCK_SIZE-WINDOW_WIDTH))
        self.y=max(0,min(player.y-WINDOW_HEIGHT//2, WORLD_HEIGHT*BLOCK_SIZE-WINDOW_HEIGHT))

# ============================================================================
# GAME
# ============================================================================

class MinecraftGame:
    def __init__(self, screen, clock):
        self.screen = screen
        self.clock  = clock
        self.font       = pygame.font.Font(None,24)
        self.font_small = pygame.font.Font(None,20)

        self.world  = World(WORLD_WIDTH,WORLD_HEIGHT)
        sx,sy       = self._find_spawn_point()
        self.player = Player(sx,sy)
        self.camera = Camera()

        self.pigs          = []
        self.dropped_items = []
        self._spawn_pigs()

        self.running         = True
        self.game_over       = False
        self.show_craft_menu = False
        self.show_inventory  = False
        self.show_console    = False   # F9

        log.info("Game session started")

    # ── helpers ──────────────────────────────────────────────────────────────

    def _find_spawn_point(self):
        cx=WORLD_WIDTH//2
        for y in range(WORLD_HEIGHT):
            if self.world.is_solid(cx,y): return cx,y-2
        return cx,20

    def _spawn_pigs(self):
        for _ in range(15):
            x=random.randint(10,WORLD_WIDTH-10)
            for y in range(WORLD_HEIGHT):
                if self.world.is_solid(x,y):
                    self.pigs.append(Pig(x,y-2)); break
        log.info(f"Spawned {len(self.pigs)} pigs")

    # ── events ───────────────────────────────────────────────────────────────

    def handle_events(self):
        for event in pygame.event.get():
            if event.type==pygame.QUIT:
                log.info("Window close requested"); self.running=False

            if event.type==pygame.KEYDOWN:

                # F9 — developer console
                if event.key==pygame.K_F9:
                    self.show_console=not self.show_console
                    log.debug(f"Console {'opened' if self.show_console else 'closed'}")

                # console scroll
                if self.show_console:
                    if event.key==pygame.K_UP:   log.scroll_up()
                    if event.key==pygame.K_DOWN: log.scroll_down()
                    if event.key not in (pygame.K_F9,pygame.K_UP,pygame.K_DOWN):
                        continue  # swallow other keys while console open

                # restart
                if self.game_over and event.key==pygame.K_r:
                    log.info("Player restarted game")
                    self.__init__(self.screen,self.clock); return

                if event.key==settings.keys["eat"] and not self.game_over:
                    self.player.eat_bacon()

                if event.key==settings.keys["inventory"] and not self.game_over:
                    self.show_inventory  = not self.show_inventory
                    self.show_craft_menu = False
                    log.debug(f"Inventory {'opened' if self.show_inventory else 'closed'}")

                if event.key==settings.keys["craft"] and not self.game_over:
                    self.show_craft_menu = not self.show_craft_menu
                    self.show_inventory  = False

                if self.show_craft_menu:
                    craft_keys={pygame.K_1:ToolType.SHOVEL,pygame.K_2:ToolType.PICKAXE,
                                pygame.K_3:ToolType.AXE,  pygame.K_4:ToolType.HOE,
                                pygame.K_5:ToolType.SWORD}
                    if event.key in craft_keys:
                        self.player.craft_item(craft_keys[event.key])

                mods=pygame.key.get_mods()
                if mods&pygame.KMOD_ALT:
                    tool_map={pygame.K_1:ToolType.SHOVEL,pygame.K_2:ToolType.PICKAXE,
                              pygame.K_3:ToolType.AXE,  pygame.K_4:ToolType.HOE,
                              pygame.K_5:ToolType.SWORD}
                    if event.key in tool_map:
                        t=tool_map[event.key]
                        if self.player.tools.get(t,0)>0:
                            self.player.selected_tool=t
                            log.info(f"Tool selected: {t.name}")

                if not self.show_craft_menu and not self.show_inventory:
                    if pygame.K_1<=event.key<=pygame.K_9:
                        self.player.select_hotbar_slot(event.key-pygame.K_1)

                if event.key==pygame.K_0:
                    self.player.selected_tool=None

            # mouse scroll in console
            if event.type==pygame.MOUSEWHEEL and self.show_console:
                if event.y>0: log.scroll_up(3)
                else:          log.scroll_down(3)

            if event.type==pygame.MOUSEBUTTONDOWN and not self.game_over \
                    and not self.show_inventory and not self.show_craft_menu \
                    and not self.show_console:
                mx,my=pygame.mouse.get_pos()
                wx=int((mx+self.camera.x)//BLOCK_SIZE)
                wy=int((my+self.camera.y)//BLOCK_SIZE)

                if event.button==1:
                    pig_hit=False
                    for pig in self.pigs:
                        pgx=int(pig.x//BLOCK_SIZE); pgy=int(pig.y//BLOCK_SIZE)
                        if abs(pgx-wx)<=1 and abs(pgy-wy)<=1:
                            pig.take_damage(1)
                            if not pig.is_alive():
                                dx2=int(pig.x//BLOCK_SIZE); dy2=int(pig.y//BLOCK_SIZE)
                                self.dropped_items.append(DroppedItem(dx2,dy2,ItemType.BACON))
                                self.dropped_items.append(DroppedItem(dx2,dy2,ItemType.BACON))
                                log.info("Pig killed — dropped 2x BACON")
                                self.pigs.remove(pig)
                            pig_hit=True; break
                    if not pig_hit:
                        block=self.world.get_block(wx,wy)
                        if block:
                            self.player.breaking_block=(wx,wy,block.block_type)
                            self.player.break_progress=0
                            log.debug(f"Started breaking {block.block_type.name} at ({wx},{wy})")

                elif event.button==3:
                    sel=self.player.get_selected_item()
                    if sel and isinstance(sel[0],BlockType):
                        bt,cnt=sel
                        if cnt>0:
                            self.world.place_block(wx,wy,bt)
                            new_cnt=cnt-1
                            self.player.hotbar[self.player.selected_hotbar_slot]=(bt,new_cnt) if new_cnt>0 else None
                            self.player.inventory[bt]=max(0,self.player.inventory.get(bt,1)-1)
                            log.debug(f"Placed {bt.name} at ({wx},{wy})")

            if event.type==pygame.MOUSEBUTTONUP and event.button==1:
                self.player.breaking_block=None; self.player.break_progress=0

    # ── update ───────────────────────────────────────────────────────────────

    def update(self):
        if self.game_over: return
        keys=pygame.key.get_pressed()
        self.player.update(keys,self.world)
        self.camera.update(self.player)

        if self.player.breaking_block:
            wx,wy,bt=self.player.breaking_block
            block=self.world.get_block(wx,wy)
            if block and block.block_type==bt:
                adj=BLOCK_BREAK_TIMES.get(bt,100)*self.player.get_tool_efficiency(bt)
                self.player.break_progress+=1
                if self.player.break_progress>=adj:
                    self.world.remove_block(wx,wy)
                    self.dropped_items.append(DroppedItem(wx,wy,bt))
                    log.info(f"Block {bt.name} broken at ({wx},{wy})")
                    self.player.breaking_block=None; self.player.break_progress=0
            else:
                self.player.breaking_block=None; self.player.break_progress=0

        for item in self.dropped_items[:]:
            item.update()
            ddx=item.x-self.player.x; ddy=item.y-self.player.y
            if (ddx*ddx+ddy*ddy)**0.5<PICKUP_RADIUS:
                self.player.add_to_inventory(item.item_type,1)
                self.dropped_items.remove(item)

        for pig in self.pigs: pig.update(self.world)

        if not self.player.is_alive():
            log.warn("Player died!")
            self.game_over=True

    # ── draw helpers ─────────────────────────────────────────────────────────

    def _draw_bar(self,x,y,w,h,pct,fill,bg=(80,0,0),border=(255,255,255)):
        pygame.draw.rect(self.screen,bg,   (x,y,w,h))
        pygame.draw.rect(self.screen,fill, (x,y,int(w*pct),h))
        pygame.draw.rect(self.screen,border,(x,y,w,h),1)

    def draw_ui(self):
        tc=(255,255,255)
        lines=[
            f"WASD:Move  SPACE:Jump  {pygame.key.name(settings.keys['eat']).upper()}:Eat  "
            f"{pygame.key.name(settings.keys['inventory']).upper()}:Inventory  "
            f"{pygame.key.name(settings.keys['craft']).upper()}:Craft  F9:Console  Alt+1-5:Tools  1-9:Hotbar",
            f"Pos:{self.player.get_grid_pos()} | Tool:{self.player.selected_tool.name if self.player.selected_tool else 'None'} | Break:{self.player.break_progress:.0f}",
        ]
        for i,l in enumerate(lines):
            self.screen.blit(self.font_small.render(l,True,tc),(10,10+i*20))

        hx,hy=WINDOW_WIDTH-220,10
        hp=self.player.health/MAX_HEALTH
        self.screen.blit(self.font_small.render(f"Health:{self.player.health}/{MAX_HEALTH}",True,tc),(hx,hy))
        self._draw_bar(hx,hy+20,100,15,hp,(int(255*(1-hp)),int(255*hp),0),(100,0,0))

        hgx,hgy=WINDOW_WIDTH-220,52
        hgp=self.player.hunger/MAX_HUNGER
        self.screen.blit(self.font_small.render(f"Hunger:{self.player.hunger}/{MAX_HUNGER}",True,tc),(hgx,hgy))
        self._draw_bar(hgx,hgy+20,100,15,hgp,(int(255*hgp),int(165*hgp),0),(100,50,0))

        # hotbar
        hb_y=WINDOW_HEIGHT-70; slot_w=50
        hb_x0=(WINDOW_WIDTH-slot_w*9)//2
        for i in range(self.player.hotbar_size):
            sx2=hb_x0+i*slot_w
            if i==self.player.selected_hotbar_slot:
                pygame.draw.rect(self.screen,(255,255,0),(sx2,hb_y,slot_w,slot_w),3)
            else:
                pygame.draw.rect(self.screen,(80,80,80),(sx2,hb_y,slot_w,slot_w))
            pygame.draw.rect(self.screen,tc,(sx2,hb_y,slot_w,slot_w),2)
            slot=self.player.hotbar[i]
            if slot:
                it,cnt=slot
                ic=BLOCK_COLORS[it] if isinstance(it,BlockType) else (255,180,50)
                pygame.draw.rect(self.screen,ic,(sx2+6,hb_y+6,20,20))
                pygame.draw.rect(self.screen,(0,0,0),(sx2+6,hb_y+6,20,20),1)
                self.screen.blit(self.font_small.render(it.name[:4],True,tc),(sx2+4,hb_y+28))
                self.screen.blit(self.font_small.render(str(cnt),True,(255,255,100)),(sx2+32,hb_y+32))
            self.screen.blit(self.font_small.render(str(i+1),True,(150,150,150)),(sx2+34,hb_y+2))

        if self.show_inventory:  self._draw_inventory()
        if self.show_craft_menu: self._draw_crafting_menu()
        if self.show_console:    log.draw(self.screen)

        if self.game_over:
            ov=pygame.Surface((WINDOW_WIDTH,WINDOW_HEIGHT)); ov.set_alpha(200); ov.fill((0,0,0))
            self.screen.blit(ov,(0,0))
            self.screen.blit(self.font.render("YOU DIED",True,(255,0,0)),
                             self.font.render("YOU DIED",True,(255,0,0)).get_rect(center=(WINDOW_WIDTH//2,WINDOW_HEIGHT//2-50)))
            reason="Hunger depleted" if self.player.hunger<=0 else "Fall damage"
            rt=self.font_small.render(f"Reason: {reason}",True,tc)
            self.screen.blit(rt,rt.get_rect(center=(WINDOW_WIDTH//2,WINDOW_HEIGHT//2)))
            rst=self.font_small.render("Press R to restart",True,(255,255,0))
            self.screen.blit(rst,rst.get_rect(center=(WINDOW_WIDTH//2,WINDOW_HEIGHT//2+40)))

    def _draw_inventory(self):
        tc=(255,255,255); mw,mh=560,420
        mx=(WINDOW_WIDTH-mw)//2; my=(WINDOW_HEIGHT-mh)//2
        ov=pygame.Surface((mw,mh)); ov.set_alpha(230); ov.fill((30,30,30))
        self.screen.blit(ov,(mx,my))
        pygame.draw.rect(self.screen,tc,(mx,my,mw,mh),2)
        self.screen.blit(self.font.render("Inventory  (I to close)",True,tc),(mx+10,my+10))
        slot_size=56; cols=9; pad=8; gx0=mx+pad; gy0=my+44
        all_items=[(k,v) for k,v in self.player.inventory.items() if v>0]
        all_tools=[(k,v) for k,v in self.player.tools.items() if v>0]
        for idx,(item,count) in enumerate(all_items):
            col=idx%cols; row=idx//cols
            sx2=gx0+col*(slot_size+4); sy2=gy0+row*(slot_size+4)
            pygame.draw.rect(self.screen,(60,60,60),(sx2,sy2,slot_size,slot_size))
            pygame.draw.rect(self.screen,(180,180,180),(sx2,sy2,slot_size,slot_size),1)
            ic=BLOCK_COLORS[item] if isinstance(item,BlockType) else (255,180,50)
            pygame.draw.rect(self.screen,ic,(sx2+6,sy2+6,28,28))
            pygame.draw.rect(self.screen,(0,0,0),(sx2+6,sy2+6,28,28),1)
            self.screen.blit(self.font_small.render(item.name[:5],True,tc),(sx2+3,sy2+36))
            self.screen.blit(self.font_small.render(str(count),True,(255,255,100)),(sx2+slot_size-20,sy2+slot_size-18))
        ty=gy0+(max(1,(len(all_items)+cols-1)//cols))*(slot_size+4)+8
        if all_tools:
            self.screen.blit(self.font_small.render("Tools:",True,(180,220,255)),(gx0,ty)); ty+=22
            for idx,(tool,cnt) in enumerate(all_tools):
                sx2=gx0+idx*(slot_size+4)
                pygame.draw.rect(self.screen,(50,50,80),(sx2,ty,slot_size,slot_size))
                pygame.draw.rect(self.screen,(100,150,255),(sx2,ty,slot_size,slot_size),1)
                self.screen.blit(self.font_small.render(tool.name[:6],True,tc),(sx2+3,ty+18))
                self.screen.blit(self.font_small.render(f"x{cnt}",True,(255,255,100)),(sx2+3,ty+36))

    def _draw_crafting_menu(self):
        tc=(255,255,255); mw,mh=420,420
        mx=(WINDOW_WIDTH-mw)//2; my=(WINDOW_HEIGHT-mh)//2
        ov=pygame.Surface((mw,mh)); ov.set_alpha(225); ov.fill((40,40,40))
        self.screen.blit(ov,(mx,my))
        pygame.draw.rect(self.screen,tc,(mx,my,mw,mh),2)
        self.screen.blit(self.font.render("Crafting Menu  (C to close)",True,tc),(mx+10,my+10))
        yo=my+50
        for i,(tt,recipe) in enumerate(CRAFTING_RECIPES.items()):
            self.screen.blit(self.font_small.render(f"[{i+1}] {tt.name}",True,(100,200,255)),(mx+20,yo))
            recipe_text=""; can_craft=True
            for it,n in recipe.items():
                have=self.player.get_inventory_count(it)
                recipe_text+=f"{it.name}:{have}/{n}  "
                if have<n: can_craft=False
            col=(0,255,0) if can_craft else (255,80,80)
            self.screen.blit(self.font_small.render(recipe_text,True,col),(mx+20,yo+18))
            yo+=52
        self.screen.blit(self.font_small.render("Press 1-5 to craft",True,(200,200,0)),(mx+20,my+mh-28))

    def draw(self):
        self.screen.fill((135,206,235))
        self.world.draw(self.screen,int(self.camera.x),int(self.camera.y))
        for item in self.dropped_items: item.draw(self.screen,self.camera.x,self.camera.y)
        for pig in self.pigs: pig.draw(self.screen,self.camera.x,self.camera.y)
        self.player.draw(self.screen,self.camera.x,self.camera.y)
        self.draw_ui()
        pygame.display.flip()

    def run(self):
        while self.running:
            self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(FPS)

# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    pygame.init()
    pygame.mixer.init()
    pygame.mixer.music.set_volume(settings.volume)

    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Minecraft 2D")
    clock  = pygame.time.Clock()

    log.info("=" * 50)
    log.info("Minecraft 2D — starting up")
    log.info(f"Base directory : {BASE_DIR}")
    log.info(f"Logs directory : {LOGS_DIR}")
    log.info(f"title.png path : {TITLE_IMG}  (exists={os.path.exists(TITLE_IMG)})")
    log.info("=" * 50)

    try:
        # Title screen
        title = TitleScreen(screen, clock)
        result = title.run()
        if result == "quit":
            log.info("Exiting from title screen")
            pygame.quit(); sys.exit()

        # Game
        game = MinecraftGame(screen, clock)
        game.run()

    except Exception:
        log.error("UNHANDLED EXCEPTION:")
        log.error(traceback.format_exc())
        if settings.save_crash_report:
            path = save_crash_report(sys.exc_info())
            # Show a brief crash screen
            try:
                screen.fill((20,0,0))
                font = pygame.font.Font(None, 36)
                lines = [
                    "The game has crashed!",
                    f"Crash report saved to:",
                    path,
                    "",
                    "Press any key to exit.",
                ]
                for i, line in enumerate(lines):
                    s = font.render(line, True, (255,100,100))
                    screen.blit(s, s.get_rect(center=(WINDOW_WIDTH//2, 200+i*50)))
                pygame.display.flip()
                waiting = True
                while waiting:
                    for e in pygame.event.get():
                        if e.type in (pygame.QUIT, pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                            waiting = False
            except Exception:
                pass
        pygame.quit()
        sys.exit(1)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()