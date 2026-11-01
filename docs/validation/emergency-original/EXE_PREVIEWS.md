# Окончательный EXE — 21 native-клип

EXE SHA-256: `ba6de760a9fffc412cc51913c6e2ed258adb29c737aea9e1d6216392d402deaa`. Только окончательная сборка; прежние кандидаты сюда не включены.

4754 исходных native PNG сохранены локально в `output/emergency-identity/native-final-solo` и `native-final-text`. Превью — WebP quality90, исходные размеры/порядок/тайминг; raw PNG/lossless WebP не изменялись. Одинаковые соседние кадры могут объединяться кодеком.

[Исходник/восстановление](identity-comparison.png) · [Лица всех состояний](native-face-overview.png) · [Руки без предметов и с ними](hands-with-and-without-props.png) · [Отчёт A–F](../../EMERGENCY_ORIGINAL_RELEASE.md)

| Сцена | Production duration | Native PNG | Полная анимация | Все кадры /лица |
|---|---:|---:|---|---|
| reading-v0 | 18 s | 436 | [WebP](solo/reading-v0.webp) | [кадры](reading-v0-all-frames.png) /[лица](reading-v0-all-faces.png) |
| reading-v1 | 18 s | 436 | [WebP](solo/reading-v1.webp) | [кадры](reading-v1-all-frames.png) /[лица](reading-v1-all-faces.png) |
| reading-v2 | 18 s | 436 | [WebP](solo/reading-v2.webp) | [кадры](reading-v2-all-frames.png) /[лица](reading-v2-all-faces.png) |
| phone_solvnox-v0 | 13 s | 317 | [WebP](solo/phone_solvnox-v0.webp) | [кадры](phone_solvnox-v0-all-frames.png) /[лица](phone_solvnox-v0-all-faces.png) |
| wand_play-v0 | 8 s | 198 | [WebP](solo/wand_play-v0.webp) | [кадры](wand_play-v0-all-frames.png) /[лица](wand_play-v0-all-faces.png) |
| wand_play-v1 | 8 s | 198 | [WebP](solo/wand_play-v1.webp) | [кадры](wand_play-v1-all-frames.png) /[лица](wand_play-v1-all-faces.png) |
| wand_play-v2 | 8 s | 198 | [WebP](solo/wand_play-v2.webp) | [кадры](wand_play-v2-all-frames.png) /[лица](wand_play-v2-all-faces.png) |
| wand_play-v3 | 8 s | 198 | [WebP](solo/wand_play-v3.webp) | [кадры](wand_play-v3-all-frames.png) /[лица](wand_play-v3-all-faces.png) |
| shy-v0 | 5.5 s | 139 | [WebP](solo/shy-v0.webp) | [кадры](shy-v0-all-frames.png) /[лица](shy-v0-all-faces.png) |
| shy-v1 | 5.5 s | 139 | [WebP](solo/shy-v1.webp) | [кадры](shy-v1-all-frames.png) /[лица](shy-v1-all-faces.png) |
| shy-v2 | 5.5 s | 139 | [WebP](solo/shy-v2.webp) | [кадры](shy-v2-all-frames.png) /[лица](shy-v2-all-faces.png) |
| annoyed-v0 | 4.5 s | 115 | [WebP](solo/annoyed-v0.webp) | [кадры](annoyed-v0-all-frames.png) /[лица](annoyed-v0-all-faces.png) |
| annoyed-v1 | 4.5 s | 115 | [WebP](solo/annoyed-v1.webp) | [кадры](annoyed-v1-all-frames.png) /[лица](annoyed-v1-all-faces.png) |
| annoyed-v2 | 4.5 s | 115 | [WebP](solo/annoyed-v2.webp) | [кадры](annoyed-v2-all-frames.png) /[лица](annoyed-v2-all-faces.png) |
| daydream-v0 | 9 s | 222 | [WebP](solo/daydream-v0.webp) | [кадры](daydream-v0-all-frames.png) /[лица](daydream-v0-all-faces.png) |
| idle-v0 | 6 s | 150 | [WebP](solo/idle-v0.webp) | [кадры](idle-v0-all-frames.png) /[лица](idle-v0-all-faces.png) |
| hover-v0 | 6 s | 150 | [WebP](solo/hover-v0.webp) | [кадры](hover-v0-all-frames.png) /[лица](hover-v0-all-faces.png) |
| thinking-v0 | 6 s | 150 | [WebP](solo/thinking-v0.webp) | [кадры](thinking-v0-all-frames.png) /[лица](thinking-v0-all-faces.png) |
| working-v0 | 6 s | 150 | [WebP](solo/working-v0.webp) | [кадры](working-v0-all-frames.png) /[лица](working-v0-all-faces.png) |

## Windows compositor поверх текста

| Сцена | Native PNG | Полная анимация |
|---|---:|---|
| reading-v0 | 436 | [WebP](text/reading-v0.webp) |
| phone_solvnox-v0 | 317 | [WebP](text/phone_solvnox-v0.webp) |

Compositor capture ограничен собственным непрозрачным тестовым окном; чужие перекрывающие окна проверяются до/после capture. Native monitor DPR1.25; полный sprite195 logical px. Дополнительные DPR/scale plates — offscreen renderer, не переключение монитора.

Полные all-frame contact sheets содержат обзорные thumbnails. Facial sheets — fixed-region crops исходных native PNG, без warp или дорисовки. Неизменность geometry дополнительно проверяется source pixel/anchor tests.
