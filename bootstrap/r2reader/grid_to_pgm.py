"""grid_to_pgm.py -- the Plate's text (the 2026-10-22 change set): a finder
who reads a page with a loupe types its module grid as text, H lines of W
characters, 1 = ink, 0 = white, and this one line writes the P5 PGM the
stage-2 reader reads: one pixel per module, 255 white, 0 ink, six white
modules on every side.  It reads grid.txt and writes grid.pgm in the
working directory (literals, not arguments: 2026-10-23).  As the Plate
prints it:  python3 -c "LINE"   (LINE = the line below)"""
r=open('grid.txt').read().split();w=max(map(len,r))+12;e=['']*6;open('grid.pgm','wb').write(b'P5 %d %d 255\n'%(w,len(r)+12)+bytes(255*(c<'1')for l in e+r+e for c in('0'*6+l).ljust(w,'0')))
