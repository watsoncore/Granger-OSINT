# Записи финального EXE

SHA-256: `da5c869384ce1ff51d310813f42b40d5e834143a4f8d52fc836fa0b7649f4cef`.

Реальные живые Qt-виджеты EXE, обычные production clocks, отдельный пустой профиль. Каждый клип — фиксированный общий alpha crop без масштабирования, перестановки и придуманных кадров. Публичный WebP quality 90 сохраняет оригинальный порядок и время кадров; исходные PNG/lossless сохранены локально. DPR монитора 1.25.

## 195 logical px

| Цикл | Секунды записи | Кадры PNG | Фактические fps |
| --- | ---: | ---: | ---: |
| [reading-v0](exe/reading-v0.webp) | 18.270 | 436 | 23.81 |
| [reading-v1](exe/reading-v1.webp) | 18.271 | 436 | 23.81 |
| [reading-v2](exe/reading-v2.webp) | 18.271 | 436 | 23.81 |
| [shy-v0](exe/shy-v0.webp) | 5.796 | 139 | 23.81 |
| [shy-v1](exe/shy-v1.webp) | 5.796 | 139 | 23.81 |
| [shy-v2](exe/shy-v2.webp) | 5.795 | 139 | 23.81 |
| [annoyed-v0](exe/annoyed-v0.webp) | 4.785 | 115 | 23.83 |
| [annoyed-v1](exe/annoyed-v1.webp) | 4.788 | 115 | 23.81 |
| [annoyed-v2](exe/annoyed-v2.webp) | 4.789 | 115 | 23.81 |
| [wand_play-v0](exe/wand_play-v0.webp) | 8.275 | 197 | 23.69 |
| [wand_play-v1](exe/wand_play-v1.webp) | 8.273 | 198 | 23.81 |
| [wand_play-v2](exe/wand_play-v2.webp) | 8.273 | 198 | 23.81 |
| [wand_play-v3](exe/wand_play-v3.webp) | 8.274 | 195 | 23.45 |
| [phone_solvnox-v0](exe/phone_solvnox-v0.webp) | 13.272 | 316 | 23.73 |
| [daydream-v0](exe/daydream-v0.webp) | 9.283 | 222 | 23.81 |
| [thinking-v0](exe/thinking-v0.webp) | 6.259 | 150 | 23.81 |
| [working-v0](exe/working-v0.webp) | 6.258 | 150 | 23.81 |
| [idle-v0](exe/idle-v0.webp) | 6.269 | 150 | 23.77 |
| [hover-v0](exe/hover-v0.webp) | 6.258 | 150 | 23.81 |
| [happy-v0](exe/happy-v0.webp) | 6.258 | 150 | 23.81 |
| [error-v0](exe/error-v0.webp) | 6.259 | 150 | 23.81 |
| [cast-v0](exe/cast-v0.webp) | 2.772 | 67 | 23.81 |
| [avada-v0](exe/avada-v0.webp) | 3.485 | 84 | 23.81 |
| [yawn-v0](exe/yawn-v0.webp) | 2.394 | 58 | 23.81 |
| [sleep-v0](exe/sleep-v0.webp) | 60.922 | 735 | 12.05 |
| [wake-v0](exe/wake-v0.webp) | 0.923 | 23 | 23.85 |
| [leave-v0](exe/leave-v0.webp) | 14.994 | 358 | 23.81 |
| [away-v0](exe/away-v0.webp) | 6.257 | 150 | 23.81 |
| [return-v0](exe/return-v0.webp) | 1.890 | 46 | 23.81 |
| [settle-v0](exe/settle-v0.webp) | 0.587 | 15 | 23.84 |
| [walk-v0](exe/walk-v0.webp) | 6.296 | 151 | 23.82 |

## 100 logical px

| Цикл | Секунды записи | Кадры PNG | Фактические fps |
| --- | ---: | ---: | ---: |
| [reading-v0](exe-100/reading-v0.webp) | 18.269 | 436 | 23.81 |
| [phone_solvnox-v0](exe-100/phone_solvnox-v0.webp) | 13.273 | 317 | 23.81 |
| [wand_play-v0](exe-100/wand_play-v0.webp) | 8.273 | 198 | 23.81 |
| [shy-v0](exe-100/shy-v0.webp) | 5.796 | 139 | 23.81 |
| [annoyed-v0](exe-100/annoyed-v0.webp) | 4.787 | 115 | 23.81 |

## 160 logical px

| Цикл | Секунды записи | Кадры PNG | Фактические fps |
| --- | ---: | ---: | ---: |
| [reading-v0](exe-160/reading-v0.webp) | 18.270 | 436 | 23.81 |
| [phone_solvnox-v0](exe-160/phone_solvnox-v0.webp) | 13.271 | 317 | 23.81 |
| [wand_play-v0](exe-160/wand_play-v0.webp) | 8.274 | 198 | 23.81 |
| [shy-v0](exe-160/shy-v0.webp) | 5.795 | 139 | 23.81 |
| [annoyed-v0](exe-160/annoyed-v0.webp) | 4.785 | 115 | 23.82 |

## Мышь и физика

[Drag / hover / направления взгляда](input/drag-interrupt.webp) — 528 IPC snapshots, 55.443 s, фактические 9.523 fps; события до 21.5 s, затем сохранён спокойный хвост. Это отдельная запись с переменной частотой; скорость воспроизведения не ускорена.

[Ключевые реальные реакции](input/input-events.png).

## Проверка без реквизита

[Руки чтения](hands-only/reading-v0-timeline.png) · [Руки телефона](hands-only/phone_solvnox-v0-timeline.png) · [Руки палочки](hands-only/wand_play-v1-timeline.png). Это тот же production renderer и те же суставы, props скрыты для диагностики. Эти plates — offscreen, не native-запись.
