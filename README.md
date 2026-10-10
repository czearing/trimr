# Trimr

Trim triangles, keep the look. Like VRAMr, but for meshes.

Trimr finds the meshes that put the most triangles on screen (trees, rocks, cliffs, ruins) and writes lighter copies into a separate Mod Organizer 2 mod. Your originals are never touched. Skyrim SE and VR.

## How it works

1. **Rank.** Reads your load order and counts every placed exterior reference. Cost = placed count x triangles.
2. **Reduce.** Removes triangles only. UVs, normals, tangents, vertex colors, textures, shaders and collision stay exactly as they were.
3. **Check.** Each result is rendered next to the original from 8 angles with the real textures. A mesh ships only if shape, leaf coverage, surface depth and texture placement all match. Otherwise it keeps its original.

## Use

1. Download the latest release, unzip anywhere. You need Python 3.10+. First run installs `numpy` and `pillow`.
2. Close the game, run `Trimr.bat`, pick a preset and what to trim.
3. In MO2 enable **Trimr Output** and drag it above the mods listed in `trimr\report.md`.

Undo: disable or delete **Trimr Output**.

## Presets

| Preset | Triangles removed on the meshes it touches | Checks |
|---|---|---|
| `quality` | about 33% | strictest |
| `balanced` (default) | about 46% | strict |
| `performance` | about 57% | standard |
| `extreme` | about 63% | loosest |

Measured on the 60 heaviest meshes of one heavily modded VR list. Yours will differ. At every preset a mesh must pass the check at that preset's strictness, or it keeps its original.

## Command line

```
python -m trimr analyze                       rank what costs most, changes nothing
python -m trimr run --preset performance      reduce
python -m trimr run --targets trees,rocks     choose: trees, foliage, rocks, buildings, other
python -m trimr run --only-mods "Mod A,Mod B" --skip-mods "Mod C" --max-meshes 100
python -m trimr run --enable                  also add the mod to the profile (MO2 closed)
python -m trimr undo
```

Options: `--instance`, `--profile`, `--ignore`, `--workers`, `--fresh`.

## Limits

- Loose mesh files only. Meshes inside BSA archives are not read.
- Static, non-skinned shapes. Armor, bodies and meshes with built-in LOD levels are skipped.
- The check is an offline render. It has no lighting, shaders or wind. Test in game, and run Trimr last, after other mod changes.
- If you use DynDOLOD, regenerate after reducing so LOD matches.

## Build

`build.bat` (Visual Studio Build Tools and CMake) builds `reducer\build\trimr-reduce.exe`.

## License

GPL-3.0. Uses [nifly](https://github.com/ousnius/nifly) (GPL-3.0) and [meshoptimizer](https://github.com/zeux/meshoptimizer) (MIT).
