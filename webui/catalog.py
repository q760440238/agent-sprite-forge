"""Server-owned choices and validation rules for the Sprite Forge workbench."""

from __future__ import annotations

from typing import Final


TARGET_MODES: Final[dict[str, list[str]]] = {
    "creature": ["single", "evolution", "idle", "combat", "walk", "actions"],
    "player": ["player", "player_walk", "player_sheet", "player_actions"],
    "npc": ["npc", "npc_walk"],
    "asset": [
        "single", "idle", "cast", "attack", "hurt", "combat", "walk", "run",
        "hover", "charge", "projectile", "impact", "explode", "death", "fx", "sheet",
    ],
}

TARGET_LABELS: Final[dict[str, str]] = {
    "creature": "怪物 / 生物",
    "player": "玩家角色",
    "npc": "NPC",
    "asset": "技能 / 道具 / 特效",
}

MODE_LABELS: Final[dict[str, str]] = {
    "single": "静态单体",
    "evolution": "进化阶段",
    "idle": "待机循环",
    "combat": "战斗动作",
    "walk": "行走循环",
    "actions": "动作组合",
    "player": "主角立绘",
    "player_walk": "主角行走",
    "player_sheet": "四方向行走",
    "player_actions": "主角动作",
    "npc": "NPC 单体",
    "npc_walk": "NPC 行走",
    "cast": "施法",
    "attack": "攻击",
    "hurt": "受击",
    "run": "奔跑",
    "hover": "悬浮",
    "charge": "蓄力",
    "projectile": "投射物",
    "impact": "命中特效",
    "explode": "爆裂特效",
    "death": "消散 / 倒下",
    "fx": "通用特效",
    "sheet": "连续动画",
}

NPC_ROLES: Final[dict[str, str]] = {
    "starter": "引导导师",
    "shop": "商店主人",
    "healer": "治疗师",
    "summoner": "召唤师",
    "sage": "贤者",
    "trainer": "训练师",
    "gym_leader": "首领",
    "villager": "村民",
    "guard": "守卫",
}

# Only compact grids are offered: they are easier for image models to lay out
# consistently than a long row, while still covering detailed 32-frame loops.
FRAME_PRESETS: Final[list[dict[str, int | str]]] = [
    {"count": 1, "rows": 1, "cols": 1, "label": "1 帧 · 静态"},
    {"count": 4, "rows": 2, "cols": 2, "label": "4 帧 · 2 × 2"},
    {"count": 6, "rows": 2, "cols": 3, "label": "6 帧 · 2 × 3"},
    {"count": 8, "rows": 2, "cols": 4, "label": "8 帧 · 2 × 4"},
    {"count": 9, "rows": 3, "cols": 3, "label": "9 帧 · 3 × 3"},
    {"count": 12, "rows": 3, "cols": 4, "label": "12 帧 · 3 × 4"},
    {"count": 16, "rows": 4, "cols": 4, "label": "16 帧 · 4 × 4"},
    {"count": 20, "rows": 4, "cols": 5, "label": "20 帧 · 4 × 5"},
    {"count": 24, "rows": 4, "cols": 6, "label": "24 帧 · 4 × 6"},
    {"count": 25, "rows": 5, "cols": 5, "label": "25 帧 · 5 × 5"},
    {"count": 32, "rows": 4, "cols": 8, "label": "32 帧 · 4 × 8"},
]
FRAME_PRESET_BY_COUNT: Final[dict[int, dict[str, int | str]]] = {
    int(preset["count"]): preset for preset in FRAME_PRESETS
}

# Modes with semantic layouts retain their original grid when that frame count
# is selected. Other frame counts use the explicit custom-grid prompt path.
DEFAULT_FRAME_COUNTS: Final[dict[str, int]] = {
    "single": 1,
    "player": 1,
    "npc": 1,
    "evolution": 4,
    "idle": 4,
    "combat": 4,
    "walk": 4,
    "actions": 4,
    "player_walk": 4,
    "player_actions": 4,
    "npc_walk": 4,
    "attack": 4,
    "hurt": 4,
    "hover": 4,
    "charge": 4,
    "projectile": 4,
    "impact": 4,
    "explode": 4,
    "fx": 4,
    "cast": 6,
    "death": 6,
    "player_sheet": 16,
}
FIXED_FRAME_COUNTS: Final[dict[str, int]] = {
    "single": 1,
    "player": 1,
    "npc": 1,
    "evolution": 4,
    "player_sheet": 16,
}

SIZE_OPTIONS: Final[set[str]] = {
    "1024x1024",
    "1536x1024",
    "1024x1536",
    "2048x2048",
}

DEFAULT_STYLE_ID = "retro_16bit"
ART_STYLES: Final[list[dict[str, str]]] = [
    {"id": "retro_8bit", "label": "8-bit 主机像素", "group": "像素", "prompt": "8-bit console pixel art, a tightly limited palette, crisp hard edges, readable silhouettes"},
    {"id": "retro_16bit", "label": "16-bit JRPG", "group": "像素", "prompt": "16-bit JRPG pixel art, saturated palette, crisp dark outlines, controlled highlights"},
    {"id": "arcade_32bit", "label": "32-bit 街机", "group": "像素", "prompt": "32-bit arcade sprite art, expressive poses, rich shading, sharp readable forms"},
    {"id": "handheld_rpg", "label": "掌机 RPG", "group": "像素", "prompt": "handheld RPG pixel art, compact readable forms, selective highlights, balanced color clusters"},
    {"id": "tactical_pixel", "label": "战棋像素", "group": "像素", "prompt": "tactical RPG pixel art, clear class readability, disciplined palette, high contrast equipment details"},
    {"id": "pixel_isometric", "label": "等距像素", "group": "像素", "prompt": "isometric-inspired pixel art, clean geometric volumes, consistent light direction, deliberate pixel clusters"},
    {"id": "dark_fantasy_pixel", "label": "暗黑奇幻像素", "group": "像素", "prompt": "dark fantasy pixel art, muted jewel tones, dramatic rim light, strong silhouette without graphic violence"},
    {"id": "cozy_pixel", "label": "治愈像素", "group": "像素", "prompt": "cozy pixel art, warm inviting palette, gentle lighting, charming but readable game silhouettes"},
    {"id": "cyberpunk_pixel", "label": "霓虹赛博像素", "group": "像素", "prompt": "cyberpunk pixel art, neon accents on dark materials, electric cyan and magenta lighting, precise silhouette"},
    {"id": "noir_pixel", "label": "黑色电影像素", "group": "像素", "prompt": "noir pixel art, restrained monochrome palette with one accent color, dramatic value contrast, cinematic ink-like shadows"},
    {"id": "retro_gameboy", "label": "GameBoy 四色", "group": "像素", "prompt": "Game Boy pixel art, four-tone green palette, sharp dithering, high-contrast readable forms"},
    {"id": "neo_geo", "label": "Neo Geo 格斗", "group": "像素", "prompt": "Neo Geo fighting game pixel art, fluid animation poses, rich color gradients, bold character outlines"},
    {"id": "snes_rpg", "label": "SNES RPG 经典", "group": "像素", "prompt": "SNES RPG pixel art, vibrant 16-color palette clusters, detailed equipment, expressive character poses"},
    {"id": "metroidvania", "label": "银河恶魔城", "group": "像素", "prompt": "Metroidvania pixel art, atmospheric lighting, detailed sprite animation, gothic architecture details"},
    {"id": "stardew_valley", "label": "星露谷物语", "group": "热门游戏", "prompt": "Stardew Valley pixel art style, warm rustic palette, charming farm life aesthetic, cozy readable sprites"},
    {"id": "terraria", "label": "泰拉瑞亚", "group": "热门游戏", "prompt": "Terraria pixel art style, detailed adventure sprites, vibrant exploration palette, crisp item definition"},
    {"id": "dont_starve", "label": "饥荒", "group": "热门游戏", "prompt": "Don't Starve art style, hand-drawn gothic charm, scratchy linework, Burton-esque dark whimsy"},
    {"id": "hollow_knight", "label": "空洞骑士", "group": "热门游戏", "prompt": "Hollow Knight art style, hand-drawn insect forms, moody atmospheric lighting, elegant character silhouettes"},
    {"id": "celeste", "label": "蔚蓝", "group": "热门游戏", "prompt": "Celeste pixel art style, expressive character animation, atmospheric environment palette, precise platformer sprites"},
    {"id": "undertale", "label": "传说之下", "group": "热门游戏", "prompt": "Undertale pixel art style, charming expressive sprites, quirky character design, warm nostalgic palette"},
    {"id": "isaac", "label": "以撒的结合", "group": "热门游戏", "prompt": "The Binding of Isaac art style, hand-drawn grotesque charm, bold outlines, quirky disturbing aesthetic"},
    {"id": "dead_cells", "label": "死亡细胞", "group": "热门游戏", "prompt": "Dead Cells pixel art style, fluid combat animation, gothic decay aesthetic, high-contrast dramatic lighting"},
    {"id": "shovel_knight", "label": "铲子骑士", "group": "热门游戏", "prompt": "Shovel Knight pixel art style, NES-inspired palette limitations, crisp retro animation, classic adventure aesthetic"},
    {"id": "hades", "label": "哈迪斯", "group": "热门游戏", "prompt": "Hades art style, bold painterly rendering, dynamic character portraits, rich Greek mythology aesthetic"},
    {"id": "bastion", "label": "堡垒", "group": "热门游戏", "prompt": "Bastion art style, painterly hand-drawn rendering, warm fantasy palette, isometric adventure aesthetic"},
    {"id": "cuphead", "label": "茶杯头", "group": "热门游戏", "prompt": "Cuphead art style, 1930s rubber hose animation, hand-drawn cel animation, vintage cartoon aesthetic"},
    {"id": "ori", "label": "奥日", "group": "热门游戏", "prompt": "Ori art style, luminous hand-painted rendering, ethereal forest lighting, elegant fluid animation"},
    {"id": "rayman", "label": "雷曼", "group": "热门游戏", "prompt": "Rayman Legends art style, hand-painted UbiArt framework, vibrant cartoon aesthetic, expressive character animation"},
    {"id": "minecraft", "label": "我的世界", "group": "热门游戏", "prompt": "Minecraft art style, blocky voxel-inspired 2D, simple pixelated forms, iconic cubic silhouettes"},
    {"id": "pokemon", "label": "宝可梦", "group": "热门游戏", "prompt": "creature collection game sprite art, charming monster design, balanced readable forms, vibrant colorful palette, cute fantasy creatures"},
    {"id": "realistic_fantasy", "label": "写实奇幻", "group": "写实", "prompt": "realistic fantasy game art, detailed texture rendering, natural lighting, grounded magical realism aesthetic"},
    {"id": "realistic_medieval", "label": "写实中世纪", "group": "写实", "prompt": "realistic medieval game art, authentic armor details, historical weapon accuracy, natural material textures"},
    {"id": "realistic_tactical", "label": "写实战术", "group": "写实", "prompt": "realistic tactical game art, modern military equipment detail, practical gear rendering, subdued professional palette"},
    {"id": "realistic_survival", "label": "写实生存", "group": "写实", "prompt": "realistic survival game art, weathered equipment texture, natural environment integration, practical utility design"},
    {"id": "realistic_western", "label": "写实西部", "group": "写实", "prompt": "realistic western game art, authentic frontier details, dusty leather texture, historical period accuracy"},
    {"id": "realistic_samurai", "label": "写实武士", "group": "写实", "prompt": "realistic samurai game art, detailed katana craftsmanship, authentic armor plates, traditional Japanese aesthetic"},
    {"id": "realistic_knight", "label": "写实骑士", "group": "写实", "prompt": "realistic knight game art, detailed plate armor, historical European arms, metallic material rendering"},
    {"id": "realistic_pirate", "label": "写实海盗", "group": "写实", "prompt": "realistic pirate game art, weathered nautical equipment, authentic naval warfare details, oceanic color palette"},
    {"id": "realistic_sci_fi", "label": "写实科幻", "group": "写实", "prompt": "realistic sci-fi game art, functional technology design, believable future materials, grounded speculation aesthetic"},
    {"id": "realistic_cyberpunk", "label": "写实赛博", "group": "写实", "prompt": "realistic cyberpunk game art, gritty urban tech details, practical augmentation design, weathered future aesthetic"},
    {"id": "realistic_post_apoc", "label": "写实末世", "group": "写实", "prompt": "realistic post-apocalyptic game art, scavenged equipment details, environmental wear, survival-focused design"},
    {"id": "realistic_historical", "label": "写实历史", "group": "写实", "prompt": "realistic historical game art, period-accurate costume details, authentic cultural elements, documentary visual quality"},
    {"id": "realistic_warrior", "label": "写实战士", "group": "写实", "prompt": "realistic warrior game art, battle-worn equipment, practical combat gear, muscular anatomy definition"},
    {"id": "realistic_archer", "label": "写实弓箭手", "group": "写实", "prompt": "realistic archer game art, detailed bow mechanics, practical quiver design, focused hunter aesthetic"},
    {"id": "realistic_mage", "label": "写实法师", "group": "写实", "prompt": "realistic mage game art, scholarly robed details, ancient tome rendering, subtle mystical elements"},
    {"id": "realistic_rogue", "label": "写实刺客", "group": "写实", "prompt": "realistic rogue game art, practical stealth gear, concealed weapon details, shadowy operative aesthetic"},
    {"id": "realistic_barbarian", "label": "写实野蛮人", "group": "写实", "prompt": "realistic barbarian game art, tribal armor details, raw material textures, primal warrior aesthetic"},
    {"id": "realistic_monk", "label": "写实武僧", "group": "写实", "prompt": "realistic monk game art, martial arts discipline, simple robed details, focused spiritual aesthetic"},
    {"id": "realistic_paladin", "label": "写实圣騎士", "group": "写实", "prompt": "realistic paladin game art, blessed armor details, holy symbol rendering, righteous warrior aesthetic"},
    {"id": "realistic_ranger", "label": "写实游侠", "group": "写实", "prompt": "realistic ranger game art, wilderness survival gear, natural camouflage details, tracker aesthetic"},
    {"id": "horror_silent_hill", "label": "寂静岭风格", "group": "恐怖", "prompt": "atmospheric fog game art, industrial decay aesthetic, rusted metal texture, muted gray palette, mysterious misty environment"},
    {"id": "horror_resident_evil", "label": "生化危机风格", "group": "恐怖", "prompt": "Resident Evil art style, survival horror aesthetic, detailed bio-organic design, dark claustrophobic atmosphere"},
    {"id": "horror_dead_space", "label": "死亡空间风格", "group": "恐怖", "prompt": "Dead Space art style, sci-fi horror fusion, necromorph-inspired design, industrial space station aesthetic"},
    {"id": "horror_outlast", "label": "逃生风格", "group": "恐怖", "prompt": "found-footage game art style, abandoned facility atmosphere, documentary camera aesthetic, dim lighting, tense survival mood"},
    {"id": "horror_amnesia", "label": "失忆症风格", "group": "恐怖", "prompt": "Amnesia art style, Victorian gothic horror, sanity-bending visuals, dark historical atmosphere"},
    {"id": "horror_layers_fear", "label": "层层恐惧风格", "group": "恐怖", "prompt": "surreal art gallery aesthetic, distorted perspective, painterly brush strokes, Victorian mansion atmosphere, twisted architecture"},
    {"id": "horror_soma", "label": "索玛风格", "group": "恐怖", "prompt": "SOMA art style, underwater sci-fi horror, existential dread mood, deep-sea isolation aesthetic"},
    {"id": "horror_little_nightmares", "label": "小小梦魇风格", "group": "恐怖", "prompt": "Little Nightmares art style, grotesque whimsy, distorted proportions, eerie童话 horror aesthetic"},
    {"id": "horror_darkest_dungeon", "label": "暗黑地牢风格", "group": "恐怖", "prompt": "Darkest Dungeon art style, gothic comic horror, bold ink shadows, stress-inducing dark fantasy"},
    {"id": "horror_bloodborne", "label": "血源诅咒风格", "group": "恐怖", "prompt": "Bloodborne art style, Victorian gothic horror, eldritch cosmic dread, baroque monster design"},
    {"id": "horror_alan_wake", "label": "心灵杀手风格", "group": "恐怖", "prompt": "Alan Wake art style, Stephen King-inspired horror, darkness manifestation, thriller novelist aesthetic"},
    {"id": "horror_fatal_frame", "label": "零系列风格", "group": "恐怖", "prompt": "Fatal Frame art style, Japanese ghost horror, spirit photography aesthetic, traditional haunted mansion mood"},
    {"id": "horror_clock_tower", "label": "钟楼惊魂风格", "group": "恐怖", "prompt": "Clock Tower art style, slasher survival horror, gothic mansion atmosphere, relentless pursuer dread"},
    {"id": "horror_fnaf", "label": "玩具熊午夜后宫风格", "group": "恐怖", "prompt": "Five Nights at Freddy's art style, animatronic horror, security camera aesthetic, jumpscares tension design"},
    {"id": "horror_limbo", "label": "地狱边境风格", "group": "恐怖", "prompt": "LIMBO art style, monochrome silhouette horror, minimalist environmental danger, film grain atmosphere"},
    {"id": "horror_inside", "label": "Inside风格", "group": "恐怖", "prompt": "INSIDE art style, dystopian body horror, muted color dread, oppressive industrial atmosphere"},
    {"id": "horror_cry_of_fear", "label": "恐惧之泣风格", "group": "恐怖", "prompt": "Cry of Fear art style, urban psychological horror, monster manifestation design, Nordic gloom aesthetic"},
    {"id": "horror_project_zero", "label": "零濡鸦之巫女风格", "group": "恐怖", "prompt": "Project Zero art style, Japanese wet ghost horror, camera obscura aesthetic, cursed ritual atmosphere"},
    {"id": "horror_dead_by_daylight", "label": "黎明杀机风格", "group": "恐怖", "prompt": "multiplayer survival game art, dark forest atmosphere, moonlit foggy environment, mysterious realm aesthetic, shadowy figures"},
    {"id": "horror_phasmophobia", "label": "恐鬼症风格", "group": "恐怖", "prompt": "Phasmophobia art style, ghost hunting equipment, paranormal investigation aesthetic, co-op terror mood"},
    {"id": "realistic_jiangshi", "label": "林正英僵尸", "group": "2D现实", "prompt": "photorealistic Chinese hopping vampire jiangshi, Qing dynasty costume, pale face, traditional talisman, Hong Kong cinema style, high detail"},
    {"id": "realistic_alien", "label": "外星人", "group": "2D现实", "prompt": "photorealistic alien creature, extraterrestrial being, sci-fi character design, cinematic quality, high detail"},
    {"id": "realistic_amazon_warrior", "label": "亚马逊丛林战士", "group": "2D现实", "prompt": "photorealistic Amazon jungle warrior, tribal costume, indigenous weapons, rainforest background, cinematic photography, high detail"},
    {"id": "realistic_resident_evil", "label": "生化危机", "group": "2D现实", "prompt": "photorealistic survival action movie style, bio-hazard laboratory environment, protective tactical gear, cinematic quality, high detail"},
    {"id": "realistic_medieval", "label": "中世纪现实", "group": "2D现实", "prompt": "photorealistic medieval era, historical costume, armor and weapons, European middle ages, period drama quality, high detail"},
    {"id": "realistic_medieval_witch", "label": "中世纪女巫", "group": "2D现实", "prompt": "photorealistic medieval witch, historical costume, occult atmosphere, dark fantasy realism, period drama quality, high detail"},
    {"id": "realistic_three_kingdoms", "label": "三国现实", "group": "2D现实", "prompt": "photorealistic Three Kingdoms era warrior, ancient Chinese armor, Han dynasty military costume, historical epic quality, high detail"},
    {"id": "realistic_modern_city", "label": "现代都市", "group": "2D现实", "prompt": "photorealistic modern city street, contemporary architecture, urban landscape photography, high detail, professional photo"},
    {"id": "realistic_forest", "label": "森林环境", "group": "2D现实", "prompt": "photorealistic forest environment, dense woodland, natural trees, nature photography, high detail"},
    {"id": "realistic_desert", "label": "沙漠场景", "group": "2D现实", "prompt": "photorealistic desert landscape, sand dunes, arid environment, landscape photography, high detail"},
    {"id": "realistic_winter", "label": "冬季雪景", "group": "2D现实", "prompt": "photorealistic winter scene, snow covered landscape, cold weather, nature photography, high detail"},
    {"id": "realistic_night", "label": "夜景", "group": "2D现实", "prompt": "photorealistic night scene, city lights, nighttime photography, urban evening, high detail"},
    {"id": "realistic_sunset", "label": "黄昏场景", "group": "2D现实", "prompt": "photorealistic sunset scene, golden hour, warm evening light, landscape photography, high detail"},
    {"id": "realistic_industrial", "label": "工业区域", "group": "2D现实", "prompt": "photorealistic industrial area, factory buildings, urban industrial zone, architectural photography, high detail"},
    {"id": "realistic_cyberpunk_city", "label": "赛博朋克都市", "group": "2D现实", "prompt": "photorealistic cyberpunk city, neon lights, futuristic urban landscape, blade runner atmosphere, cinematic quality, high detail"},
    {"id": "realistic_steampunk", "label": "蒸汽朋克", "group": "2D现实", "prompt": "photorealistic steampunk aesthetic, Victorian industrial, brass machinery, retro-futuristic, cinematic quality, high detail"},
    {"id": "realistic_post_apocalypse", "label": "末世废土", "group": "2D现实", "prompt": "photorealistic post-apocalyptic wasteland, ruins and debris, survival atmosphere, cinematic quality, high detail"},
    {"id": "realistic_ancient_egypt", "label": "古埃及", "group": "2D现实", "prompt": "photorealistic ancient Egypt, pharaoh costume, pyramids background, historical epic quality, high detail"},
    {"id": "realistic_viking", "label": "维京战士", "group": "2D现实", "prompt": "photorealistic Viking warrior, Norse costume, battle gear, historical epic quality, high detail"},
    {"id": "realistic_samurai_era", "label": "日本武士时代", "group": "2D现实", "prompt": "photorealistic samurai era Japan, traditional armor, feudal period costume, historical drama quality, high detail"},
    {"id": "realistic_urban_supernatural", "label": "都市灵异", "group": "2D现实", "prompt": "photorealistic urban supernatural mystery, ghostly atmosphere in modern city, paranormal phenomenon, cinematic horror realism, high detail"},
    {"id": "realistic_ancient_supernatural", "label": "古代灵异", "group": "2D现实", "prompt": "photorealistic ancient supernatural mystery, haunted ancient temple, eerie spiritual atmosphere, Chinese folklore realism, cinematic quality, high detail"},
    {"id": "realistic_chinese_battlefield", "label": "中国古代战场", "group": "2D现实", "prompt": "photorealistic ancient Chinese battlefield, armored soldiers, war banners, epic historical conflict, cinematic war scene, high detail"},
    {"id": "realistic_european_battlefield", "label": "欧洲古代战场", "group": "2D现实", "prompt": "photorealistic medieval European battlefield, knights in armor, cavalry charge, epic historical war scene, cinematic quality, high detail"},
    {"id": "realistic_warcraft", "label": "魔兽世界", "group": "2D现实", "prompt": "photorealistic high fantasy MMORPG style, orc warrior with battle axe, epic fantasy creature design, cinematic game art realism, high detail"},
    {"id": "realistic_heroes_might_magic", "label": "英雄无敌", "group": "2D现实", "prompt": "photorealistic epic turn-based strategy fantasy, dragon and knight, magical realm landscape, cinematic fantasy game art, high detail"},
    {"id": "anime_cel", "label": "日系赛璐璐", "group": "插画", "prompt": "anime cel shading, clean linework, flat confident color planes, polished game-character rendering"},
    {"id": "anime_painterly", "label": "日系厚涂", "group": "插画", "prompt": "painterly anime game art, refined brush shading, luminous controlled color, clear character design"},
    {"id": "comic_ink", "label": "美漫墨线", "group": "插画", "prompt": "comic-book ink art, bold contour lines, confident hatching, punchy graphic color blocks"},
    {"id": "graphic_novel", "label": "图像小说", "group": "插画", "prompt": "graphic novel illustration, textured ink shadows, sophisticated limited palette, high visual contrast"},
    {"id": "hand_painted_rpg", "label": "手绘 RPG", "group": "插画", "prompt": "clean hand-painted RPG game art, readable brushwork, cohesive material rendering, clear forms"},
    {"id": "watercolor_fantasy", "label": "水彩奇幻", "group": "插画", "prompt": "watercolor fantasy illustration, translucent pigment texture, soft color transitions, controlled edges"},
    {"id": "gouache_storybook", "label": "绘本水粉", "group": "插画", "prompt": "gouache storybook art, matte pigment texture, warm layered colors, handcrafted illustrative charm"},
    {"id": "ink_wash", "label": "水墨", "group": "插画", "prompt": "East Asian ink wash illustration, expressive brush marks, restrained color accents, elegant negative space"},
    {"id": "woodblock_print", "label": "木刻版画", "group": "插画", "prompt": "woodblock print illustration, carved line texture, flat layered colors, artisanal graphic finish"},
    {"id": "stained_glass", "label": "彩绘玻璃", "group": "插画", "prompt": "stained-glass-inspired art, jewel-tone color segments, bold lead-like contours, luminous ornamental forms"},
    {"id": "paper_cutout", "label": "剪纸拼贴", "group": "插画", "prompt": "paper-cut collage art, layered cut-paper shapes, tactile edges, playful dimensional color blocks"},
    {"id": "flat_vector", "label": "扁平矢量", "group": "插画", "prompt": "flat vector game art, clean geometric shapes, deliberate color hierarchy, minimal precise outlines"},
    {"id": "clean_mobile", "label": "清爽手游", "group": "插画", "prompt": "clean casual mobile game art, polished shapes, bright accessible palette, highly readable silhouette"},
    {"id": "low_poly_illustration", "label": "低多边形插画", "group": "插画", "prompt": "low-poly-inspired 2D illustration, faceted planes, simplified geometry, crisp directional lighting"},
    {"id": "art_nouveau", "label": "新艺术运动", "group": "插画", "prompt": "Art Nouveau game illustration, flowing organic lines, decorative botanical details, elegant curved forms"},
    {"id": "art_deco", "label": "装饰艺术", "group": "插画", "prompt": "Art Deco game art, geometric patterns, metallic accents, bold symmetrical design, luxurious color palette"},
    {"id": "retro_poster", "label": "复古海报", "group": "插画", "prompt": "retro poster art style, bold simplified shapes, limited vibrant palette, strong graphic composition"},
    {"id": "sketch_draft", "label": "概念草图", "group": "插画", "prompt": "concept sketch art, loose confident linework, gestural marks, selective shading, design clarity"},
    {"id": "sci_fi_mecha", "label": "科幻机甲", "group": "题材", "prompt": "science-fiction mecha game art, engineered panel details, purposeful hard-surface shapes, cool technical lighting"},
    {"id": "steampunk", "label": "蒸汽朋克", "group": "题材", "prompt": "steampunk game art, brass mechanisms, leather and clockwork details, warm industrial color accents"},
    {"id": "dieselpunk", "label": "柴油朋克", "group": "题材", "prompt": "dieselpunk game art, rugged industrial forms, weathered metal, restrained military-inspired palette"},
    {"id": "gothic_fantasy", "label": "哥特奇幻", "group": "题材", "prompt": "gothic fantasy game art, ornate silhouettes, deep jewel tones, dramatic but age-appropriate atmosphere"},
    {"id": "cute_chibi", "label": "Q 版角色", "group": "题材", "prompt": "cute chibi game art, compact stylized proportions, clear facial expression, bright friendly palette"},
    {"id": "oil_painted", "label": "古典油画", "group": "题材", "prompt": "classical oil-painted game illustration, rich brush texture, deep color layering, sculpted light and shadow"},
    {"id": "horror_gothic", "label": "惊悚哥特", "group": "题材", "prompt": "horror gothic game art, dark atmospheric shadows, unsettling but age-appropriate mood, mysterious silhouettes"},
    {"id": "tribal_ethnic", "label": "部落民族", "group": "题材", "prompt": "tribal ethnic game art, traditional pattern details, earthy organic palette, cultural symbolic motifs"},
    {"id": "crystal_fantasy", "label": "水晶幻想", "group": "题材", "prompt": "crystal fantasy game art, prismatic gem-like forms, luminous refractive colors, magical crystalline details"},
    {"id": "bio_organic", "label": "生物有机", "group": "题材", "prompt": "bio-organic game art, flowing natural forms, living tissue textures, evolutionary creature design"},
]
ART_STYLE_BY_ID: Final[dict[str, dict[str, str]]] = {style["id"]: style for style in ART_STYLES}


def frame_preset(frame_count: int) -> dict[str, int | str]:
    try:
        return FRAME_PRESET_BY_COUNT[frame_count]
    except KeyError as exc:
        raise ValueError("帧数不受支持，请从预设列表中选择") from exc


def fixed_frame_count(mode: str) -> int | None:
    return FIXED_FRAME_COUNTS.get(mode)


def requires_custom_grid(mode: str, frame_count: int) -> bool:
    """Whether the CLI must receive rows/cols instead of using its legacy preset."""
    if frame_count == 1:
        return False
    return DEFAULT_FRAME_COUNTS.get(mode) != frame_count


def resolve_style(style_id: str, detail: str = "") -> tuple[str, str]:
    try:
        style = ART_STYLE_BY_ID[style_id]
    except KeyError as exc:
        raise ValueError("画风不受支持，请重新选择") from exc
    extra = " ".join(detail.split())
    prompt = style["prompt"]
    if extra:
        prompt = f"{prompt}. Additional direction: {extra}"
    return style["label"], prompt


def public_options() -> dict[str, object]:
    return {
        "targets": [
            {
                "id": target,
                "label": TARGET_LABELS[target],
                "modes": [
                    {
                        "id": mode,
                        "label": MODE_LABELS[mode],
                        "fixed_frame_count": fixed_frame_count(mode),
                        "default_frame_count": DEFAULT_FRAME_COUNTS.get(mode, 4),
                    }
                    for mode in modes
                ],
            }
            for target, modes in TARGET_MODES.items()
        ],
        "npc_roles": [
            {"id": role, "label": label} for role, label in NPC_ROLES.items()
        ],
        "frames": FRAME_PRESETS,
        "styles": [
            {"id": style["id"], "label": style["label"], "group": style["group"]}
            for style in ART_STYLES
        ],
        "default_style": DEFAULT_STYLE_ID,
    }
