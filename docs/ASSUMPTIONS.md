# Assumptions and limitations

SafeSol is a planning and teaching tool built on a deliberately simple, transparent model.
Every assumption below is visible in the app or in this file. Code: `src/compute/`.

## Vehicle presets (all values are assumptions)

| Parameter | Crewed pressurized rover | Robotic rover |
|---|---|---|
| Mass | 4000 kg | 900 kg |
| Speed | 2.0 m/s | 0.04 m/s |
| Slope limit | 20° | 20° |
| Base power | 3000 W | 120 W |
| Usable energy per sol | 60 000 Wh | 2000 Wh |
| Driving hours per sol | 8 h | 4 h |

Illustrative values chosen by the team, not specifications of any real NASA vehicle.
Every value can be changed in the app and all results update. Mars surface gravity: 3.72 m/s².

## Terrain

- The DEM is reprojected to a local equirectangular projection centred on the region, so one
  projected metre is one metre on the ground. A global equirectangular grid would stretch
  east-west distances by 1/cos(latitude), about 5% at Jezero.
- Resampled by area averaging to 25 m cells by default. Slopes depend on this cell size:
  sampling a route more finely than the DEM adds no information.

## Route model (`route.py`)

- Constant speed; no acceleration, wheel slip, rolling resistance or drivetrain losses.
- Energy = base power × time + gravitational energy for total climb. No solar charging,
  thermal or instrument loads.
- Pass/fail uses the slope along the route. The steepest ground slope in any direction is
  reported separately, because a route can be gentle along its direction but steep sideways.

## Contingency route (`pathfind.py`)

- Dijkstra on a block-averaged copy of the DEM (at most 450 cells per side; 50 m cells for a
  20 km region), 8 neighbours, cost = travel time × (1 + slope / limit).
- Steps steeper than 80% of the slope limit are blocked while planning, to absorb detail lost by
  averaging. The route is then re-checked on the full DEM; if it still fails, the app says so.
- It is a computed suggestion, not a NASA-approved traverse.

## Solar storm drill (`shielding.py`, `escape.py`)

- Events come from NASA DONKI. Most SEP detections are made by spacecraft near Earth. SafeSol
  replays them as historical scenarios on Mars; it does not claim the same flux reached Mars.
- Warning time is a user-set assumption (5 to 180 minutes) because real lead times vary by event.
- The shielding index (1 − sky view factor, 16 azimuths, horizon searched to 1.5 km) is a
  RELATIVE measure of how much open sky the terrain blocks, assuming particles arrive equally
  from all directions. It is not a radiation dose and ignores the atmosphere column, the particle
  energy spectrum and secondary radiation from the ground.
- The habitat is assumed to be a full storm shelter at a position chosen by the team.
- Terrain shelters are the highest-shielding cells not steeper than the slope limit, at least
  700 m apart. They are not validated camp sites.
- Natural caves: the Mars Global Cave Candidate Catalog lists candidate cave entrances, mostly
  around the Tharsis volcanoes. Where the region has none, SafeSol relies on terrain shielding.
