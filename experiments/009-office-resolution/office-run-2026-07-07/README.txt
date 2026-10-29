ORES-1 — Office RESolution unlock run for the Xerox AltaLink C8245
==================================================================
Goal: find out whether PJL or native PCL can reach the AltaLink's spec
1200/2400 dpi, where its PostScript path is stuck at 600 (measured, 007.6).

RUN IT
  1. Copy this whole folder to a machine that can reach the printer at
     <ip>:9100 and has `nc` (netcat).
  2. Review the script if you like:   less run_ores.sh
  3. ./run_ores.sh                     (default host <ip>)
     or ./run_ores.sh <host>           to override.
  It asks before every send; type "yes" to send, "skip" to skip.

WHAT IT SENDS (in jobs/)
  ores_query.pjl            READ-ONLY capability query — prints NOTHING;
                            the printer's reply is saved to responses/.
  ores_pspjl1200.job        J1: @PJL SET RESOLUTION=1200 + PostScript@1200.
  ores_pcl1200.pcl          J2: native PCL raster @ 1200 dpi.
  ores_pcl1200_pjlres.pcl   J3: J2 + the PJL 1200 hint.
  ores_pcl2400.pcl          J4: native PCL raster @ 2400 dpi.
  e004.ps / e006c.ps / e006bw.ps
                            007.9 different-day batch (verbatim reprints,
                            to bound the AltaLink's day-to-day variance).

Each print ejects ONE sheet. PEN-ANNOTATE the label the script prints
(e.g. "J2 PCL 1200") + the date on each sheet, and KEEP every sheet.
Every ORES sheet has both 1200/2400-grid fields and 600-grid CONTROL
fields: the 600 controls always survive; the finer-grid fields survive
only if that command path unlocked the finer grid.

AFTER PRINTING — SCAN (enhancements OFF, scan UPRIGHT):
  * ORES sheets J1-J4: on the CANON 4800 (grey). A >600-dpi print scanned
    at 1200 is undersampled and aliases no matter what the printer did, so
    the home 1200 flatbed is only a rough screen (trust just the 600-control
    fields there); J4 @2400 REQUIRES the Canon.
  * BATCH sheets: home flatbed, per their experiments (e006c/e004 COLOR
    1200 dpi; e006bw GREY 1200 dpi).
  Keep all 4 corner marks in frame. Bring back the scans +
  responses/ores_query_response.txt for analysis (analyze_ores.py).

Nothing here deletes or persistently reconfigures the printer; the PJL
settings inside each job are per-job and do not persist.

Job SHA-256 (also in ores_manifest.json) — verify integrity if unsure.
c5c35d94c0940b82a612dc48c7721130240709cce094a3438fce790d08f9ca68  e004.ps
797232ee1a51a3c8c0ddb173ee98a7f1a249e009f9cf3543adc95bf34c4c129e  e006bw.ps
15e27c95d81c7a0f703147c8d783569ebc34e60818484c88b1fd2a6c9d6d960b  e006c.ps
ed4751ca43c41dee8aef1c1d56c278a17175ca92cfec7cd8e6e22895b67d262f  ores_pcl1200.pcl
cd6f4eab3de37529e542a5de558f77bffa0d5d82166aee7b35fb4bc5edff86d7  ores_pcl1200_pjlres.pcl
a945be312b14105076b44c1020d2b94c8350308980a0a770dfba3d0f96a9b53e  ores_pcl2400.pcl
fd76f43b205e15bcf870d8076c82e347c1415238efbfdee78237d03167b15cd9  ores_pspjl1200.job
313053176c4165caff13019891e2131bbebeb5a6666c90e52a5e23759cd1e2bc  ores_query.pjl
