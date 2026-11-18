# Literature behind the parameters

Checked 2026-11-18. [V] = read in a primary source or official spec;
[S] = confirmed only in a secondary source or software docs; NF = not found.
Winstral et al. (2002) itself could not be read (paywall); its formula is
taken from Erickson et al. (2005), which uses it in the same valley.

| Topic | What we use | Source | Status |
|---|---|---|---|
| Sx formula and sign | Sx = max atan((z_j - z_0)/d) upwind; positive = sheltered | Winstral, Elder & Davis 2002, J. Hydrometeorol. 3:524-538, doi:10.1175/1525-7541(2002)003<0524:SSMOWR>2.0.CO;2; Erickson, Williams & Winstral 2005, WRR 41:W04014, doi:10.1029/2003WR002973 (eq. 3) | [V] via Erickson |
| Sx search distance | 300 m default, 100 m sensitivity | 100 m optimal in Winstral 2002 (per Broxton et al. 2015); 300 m default in MeteoIO and CHM | [S] |
| Sx direction window | 30° wide, 5° steps, averaged | Winstral 2002 as implemented in CHM | [S] |
| Drift separator (Sb) | not used yet | Winstral 2002; SMRF code | [S], exact form NF |
| TPI and slope positions | TPI = z - neighbourhood mean; classes at ±0.5 and ±1 SD; flat if slope <= 5° | Weiss 2001 (ESRI UC poster); Jenness 2006; De Reu et al. 2013, Geomorphology 186:39-49, doi:10.1016/j.geomorph.2012.12.015 | [S] |
| TPI radii | 150 m and 1,000 m (our choice) | no standard | NF |
| Transport threshold | 25 km/h on 700 hPa (ridge-top) wind | Avalanche Canada glossary "wind transport": moderate 25-40 km/h most conducive to wind slabs; Li & Pomeroy 1997, J. Appl. Meteorol. 36:205-213: dry 7.7 m/s, wet 9.9 m/s at 10 m | [V] |
| Threshold vs temperature | not used yet: Ut = 6.975 + 0.0033 (T + 27.27)^2 m/s (dry) | Li & Pomeroy 1997 as quoted by He & Ohara 2017 | [S] |
| Transport vs wind | q ∝ U^4 (total, saltation + suspension) | Pomeroy, Gray & Landine 1991, cited in Pomeroy & Brun 2001; saltation alone ∝ u*^2 (Pomeroy & Gray 1990, WRR 26:1583-1594) | [S] / [V] |
| Leeward window | ±45° of downwind (our choice) | no published standard | NF |
| Avalanche start-zone slopes | 30-45° (to 50° in alpine terrain), not used yet | Swiss data via Avalanche.org; McCammon 2009 | [S] |
| Slope and aspect | Horn 1981, Proc. IEEE 69:14-47, doi:10.1109/PROC.1981.11918 | | [V] |
| Grid convergence | measured numerically per point (~19° at Lake Louise in EPSG:3979) | Snyder 1987, USGS PP 1395 | [S] |
| DEM | MRDEM-30 DTM: Copernicus GLO-30 + resampled HRDEM lidar, CGVD2013, RMSE 1.6 m bare / 5.0 m vegetated (GLO-30-based areas) | NRCan MRDEM product specifications ed. 1.2 (2025-06-20) | [V] |
| Glacier outlines | RGI 7.0, CC BY 4.0, region 02, doi:10.5067/f6jmovy5navz; Bolch, Menounos & Wheate 2010, RSE 114:127-137 | | [V], not used yet |

Notes:
- Avalanche Canada also says strong winds (41-60 km/h) spread snow widely or
  sublimate it, so deposition does not simply grow with wind speed. M1 does
  not model this yet.
- Li & Pomeroy thresholds are for 10 m wind over open ground. Applying a
  threshold to 700 hPa wind is a proxy choice, not a published method.
