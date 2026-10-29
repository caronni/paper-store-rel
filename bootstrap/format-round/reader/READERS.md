# READERS — the format round's three reader texts (2026-10-22, reader builder)

The owner's go of 2026-10-22: "we should indeed measure out all three". This
file covers the reader side only. The generator is
`bootstrap/format-round/gen/gen_variant.py`, written by the generator builder;
its page sets are under `build/format-round/pages/`. The measurement is the
measurer's.

## Files

| file | what |
|---|---|
| `make_readers.py` | derives `reader_v3.py`, `reader_v1.py` and `reader_v2.py` from the ruled `r2reader/reader_lite_v1.py` by exact string edits, each asserted to match once |
| `reader_v3.py`, `reader_v1.py`, `reader_v2.py` | the three texts before the search: the diffs below, and nothing else |
| `run_search_v.py` + `rw_search.py` | ruling 32's search (the changeset's constrained run), pointed at one text with `VARIANT=v3\|v1\|v2`. `rw_search.py` is a byte copy of `r2reader/changeset/rw/run_search.py` with one line changed, the impure set (below). Outputs go to `build/format-round/reader/rw-VARIANT/` |
| `apply_search_v.py` | puts the winner back as `reader_VARIANT_rw.py` (the changeset's `apply_search_seed.py`, re-pointed) |
| `reader_v3_rw.py`, `reader_v1_rw.py`, `reader_v2_rw.py` | **the searched texts, the ones to measure** |
| `size_stage1_v.py` | `r2reader/changeset/size_stage1.py` unchanged; scratch goes to `build/format-round/reader/stage1-sizes/` |
| `sanity.py` | renders nominal-b030 seed 1 of every page of every set, then one pooled process run per set (the `edge.py` arrangement, below) |
| `seeds.py`, `runs_at.py` | diagnostics, never typed. `seeds.py` maps a text's seed list onto grid blocks through the render's homography. `runs_at.py` prints the thresholded runs through each bullseye centre |

## The edits common to all three texts

1. The ring list `y` is deleted. It was the module-level list of 177 ring
   modules and their expected values.
2. In `dd`, the ring check is deleted: the quality
   `n=sum(c[...]==k for x,y,k in y)` and the gate `4*n>=len(y)*3`. Every
   comb that passes the column confirmation and the frame-edge test is
   appended as a seed `(sz,z,p)`, in scan order.
3. The dedupe in `dd` reads that seed tuple: `s[1],s[2],s[3]` becomes
   `s[0],s[1],s[2]`.
4. `ld` unpacks `for x,y,p in c` in both places, and the pitch is
   `c[0][2]`.

`n` was unused outside the gate. The seed order was already scan order (`ld`
never sorts), so nothing else follows.

## V3, "axis bits moved, one flank"

- **Header list.**
  `ou=[(x,y)for x,y in i if x*y and x*x+y*y>56][:68]`. `i` is block raster
  order (y outer, x inner, −8..7), the generator's order. The two axis
  modules are the only header modules with `x*y == 0`: (−8,0) and (0,−8).
  (+8 is outside the data square.) That leaves 77 modules, of which the
  first 68 are taken.
- **Flank.** In the code, `t = (z[i+12]+z[i+13]) − (z[i]+z[i+1])`. That is
  twice the distance between the centres of the first and last ink run,
  2 × 12 modules = **24 modules** (the long form's `span_x2`). It is not 12
  modules. So the ruled `min(...)*96>=t` means a flank of at least t/96, a
  **quarter module** (the long form says so too), not the brief's "about
  1/8 module". "At least one flank ≥ 1.5 modules" is flank ≥ 1.5·t/24 =
  t/16:

      max(z[i]-z[i-1],z[i+14]-z[i+13])*16>=t

  The brief's "t/8" would be 3 modules under the code's t.
- **Unchanged.** The thirteen-run table, the tolerance, the pitch
  `16*(x+t)//3`, the column test `x<6*m`.

## V1, "the 3-wide band"

Centre row, modules dx = −6..6: the runs are 3,1,1,1,1,1,1,1,3, nine runs,
ink first and last. Their centres, in modules, are −5, −3, −2, −1, 0, 1, 2,
3, 5.

- **Span.**
  `t = (z[i+8]+z[i+9]) − (z[i]+z[i+1])` = 2 × (c8 − c0) = **20 modules**.
  This is a difference of run centres, so it does not move with the
  threshold. The ruled span had the same property.
- **No two run centres are 12 modules apart**, so t cannot stay at 24.
  The outer edges span 13 modules but move with the threshold.
- **Pitch.** To keep the pitch at 256 × module px from the two
  20-module spans: `p = 32*(x+t)//5`. That is 32·40/5 = 256 modules,
  against the ruled 16·48/3 = 256, the same length in characters.
- **Column test.** `x<5*m` keeps the ruled meaning: the column comb within
  one module of the row (5·4·Δ < 20·module).
- **Run count.** Nine runs, so `range(1+s[0],len(z)-9,2)`, which needs
  z[i+9]. No flank rule. The centre is `r+z[i+8]+z[i+9]-2`, as before.
- **The table.** Run k (k = 1..7) is expected at c_k − c0 = (k+1) modules.
  At the scale 10·2Δc = (k+1)·t:

  | run k | dx | expected (k+1)·t/10 of 10·(z[i+k]+z[i+k+1]−r) | checked |
  |---|---|---|---|
  | 1 | −3 | 2t | yes (y=2) |
  | 2 | −2 | 3t | yes (y=3) |
  | 3 | −1 | 4t | no |
  | 4 | 0 (the centre dot) | 5t | no |
  | 5 | +1 | 6t | no |
  | 6 | +2 | 7t | yes (y=7) |
  | 7 | +3 | 8t | yes (y=8) |

      abs(10*(z[i+y-1]+z[i+y]-r)-y*t)for y in(2,8,3,7)

  This mirrors the ruled comb, which leaves the centre dot and the white
  beside it unmeasured (runs 5–7 of 13; the long form says so).
- **Tolerance.** The ruled tolerance is 0.3 module + 0.6 px. At the new
  scale (20 per module-difference instead of 24) that is 0.3·t + 12:
  `(3*t+120)//10`.

## V2, "inverted"

Centre row, dx = −5..5: eleven one-module runs, ink first and last, the
centre run white. White at dx = ±6 and ±7, then the header module at −8 and
the neighbour's timing line at +8.

- **Run index.** `i` still steps over ink runs (`range(1+s[0],...,2)`), and
  runs i and i+10 are both ink. Nothing in `dd`, `ax` or `ld` assumed an
  ink centre once the ring check was gone, so nothing else changes.
- **Span.** `t = (z[i+10]+z[i+11]) − (z[i]+z[i+1])` = 2 × 10 = **20
  modules**. The pitch is `32*(x+t)//5`, the column test `x<5*m`, as in V1.
- **Both flanks ≥ 1.5 modules.** That is flank ≥ 1.5·t/20 = 3t/40:

      min(z[i]-z[i-1],z[i+12]-z[i+11])*40>=3*t

  The loop runs to `len(z)-12`.
- **The table.** Run k (k = 1..9) at k modules: `10*(z[i+k]+z[i+k+1]−r)`
  is expected at k·t. Checked: k = 1, 9, 2, 8, 3, 7. Not checked: k = 4, 5,
  6, the white centre and the ink beside it, the ruled comb's omission.

      abs(10*(z[i+y]+z[i+y+1]-r)-y*t)for y in(1,9,2,8,3,7)

  The tolerance is `(3*t+120)//10`, as in V1.

### diff: r2reader/reader_lite_v1.py → format-round/reader/reader_v3.py (verbatim)

```diff
--- r2reader/reader_lite_v1.py
+++ format-round/reader/reader_v3.py
@@ -1,3 +1,8 @@
+# reader_v3.py -- the format round's V3 'axis bits moved, one flank' reader
+# (2026-10-22, bootstrap/format-round/reader/make_readers.py from the ruled
+# text below; the ring list, the ring check and n dropped; READERS.md = the
+# diff).
+# The ruled text's header follows.
 # reader_lite_v1.py -- the typed stage-2 reader for R2-FORMAT v1 (2026-10-20,
 # the set pass: "Simplify the reader! good enough recovery, not perfect").
 # diet/v1/d06_panel21.py hand-minified (m07; by hand m08, m10-m12, m14;
@@ -52,10 +57,8 @@
  return s^2**32-1
 def fr(s,x,y):
  return s[0]+(s[2][0]*x+s[3][0]*y)//17,s[1]+(s[2][1]*x+s[3][1]*y)//17
-y=[(x,y,sum(x*x+y*y>i*i+i for i in range(7))&1<1)
- for y in range(-7,8)for x in range(-7,8)if x*x+y*y<57]
 i=[(x,y)for y in range(-8,8)for x in range(-8,8)]
-ou=[(x,y)for x,y in i if x*x+y*y>56][:68]
+ou=[(x,y)for x,y in i if x*y and x*x+y*y>56][:68]
 u=[(x,y,x+y&1)for y in range(-9,9)for x in range(-9,9)
  if{x,y}&{-9,8}]
 def ax(x,y,p,r,t):
@@ -75,7 +78,7 @@
  for i in range(j):
   for k,x in sp(c[h*i:h*i+h]):
    sz=k+2>>2
-   if[s for s in s if 16*abs(s[1]-4*k)+16*abs(s[2]-16*i)<6*s[3]]:
+   if[s for s in s if 16*abs(s[0]-4*k)+16*abs(s[1]-16*i)<6*s[2]]:
     continue
    q,a=max(0,i-x//2-2),min(j,i+x//2+3)
    m,r,t=min([(abs(r-4*(i-q)),r,t)for r,t in sp(c[h*q+sz:h*a:h])]
@@ -83,8 +86,7 @@
    if x<6*m:continue
    sz,z,p=4*k,4*(r+4*q),16*(x+t)//3
    if min(sz,z)<p//2 or sz>16*h-p//2-32 or z>16*j-p//2-32:continue
-   n=sum(c[(z+(y*p>>4)+8>>4)*h+(sz+(x*p>>4)+8>>4)]==k for x,y,k in y)
-   if 4*n>=len(y)*3:s+=[(n,sz,z,p)]
+   s+=[(sz,z,p)]
  return s
 def sp(s):
  z,p,n=[0],s[0],0
@@ -94,7 +96,7 @@
  z+=[len(s)]
  return[(r+z[i+12]+z[i+13]-2,t)for i in range(1+s[0],len(z)-14,2)
   for r,t in[(z[i]+z[i+1],z[i+12]+z[i+13]-z[i]-z[i+1])]
-  if 23<t and min(z[i]-z[i-1],z[i+14]-z[i+13])*96>=t and max(
+  if 23<t and max(z[i]-z[i-1],z[i+14]-z[i+13])*16>=t and max(
   abs(12*(z[i+y+6]+z[i+y+7]-r)-(y+6)*t)for y in(-5,5,-4,4,-3,3,-2,2)
   )<=(3*t+144)//10]
 def ft(s,x):
@@ -149,15 +151,15 @@
 def ld():
  c=dd(z.translate(bytes(x<t for t in[min(z[::97])+max(z[::97])>>1]
   for x in range(256))))
- k,k,m,n=max((sum(abs(w(ax(x,y,p,r,t)))for k,x,y,p in c),-abs(r),r,t)
+ k,k,m,n=max((sum(abs(w(ax(x,y,p,r,t)))for x,y,p in c),-abs(r),r,t)
   for r in range(-640,641,64)for t in range(4))
  r=[]
- for k,x,y,p in c:
+ for x,y,p in c:
   s=ax(x,y,p,m,n)
   r+=[s+[int(w(s)<0),(len(r),0,0)]]
  b=e
  for s in r:b=b or a(*f(s),ou,20)
- return(c[0][3]if c else 0,r),b or e
+ return(c[0][2]if c else 0,r),b or e
 e,n,s,t=b'',0,{},'?'
 while n<1:
  r=0
```

### diff: r2reader/reader_lite_v1.py → format-round/reader/reader_v1.py (verbatim)

```diff
--- r2reader/reader_lite_v1.py
+++ format-round/reader/reader_v1.py
@@ -1,3 +1,8 @@
+# reader_v1.py -- the format round's V1 'the 3-wide band' reader
+# (2026-10-22, bootstrap/format-round/reader/make_readers.py from the ruled
+# text below; the ring list, the ring check and n dropped; READERS.md = the
+# diff).
+# The ruled text's header follows.
 # reader_lite_v1.py -- the typed stage-2 reader for R2-FORMAT v1 (2026-10-20,
 # the set pass: "Simplify the reader! good enough recovery, not perfect").
 # diet/v1/d06_panel21.py hand-minified (m07; by hand m08, m10-m12, m14;
@@ -52,8 +57,6 @@
  return s^2**32-1
 def fr(s,x,y):
  return s[0]+(s[2][0]*x+s[3][0]*y)//17,s[1]+(s[2][1]*x+s[3][1]*y)//17
-y=[(x,y,sum(x*x+y*y>i*i+i for i in range(7))&1<1)
- for y in range(-7,8)for x in range(-7,8)if x*x+y*y<57]
 i=[(x,y)for y in range(-8,8)for x in range(-8,8)]
 ou=[(x,y)for x,y in i if x*x+y*y>56][:68]
 u=[(x,y,x+y&1)for y in range(-9,9)for x in range(-9,9)
@@ -75,16 +78,15 @@
  for i in range(j):
   for k,x in sp(c[h*i:h*i+h]):
    sz=k+2>>2
-   if[s for s in s if 16*abs(s[1]-4*k)+16*abs(s[2]-16*i)<6*s[3]]:
+   if[s for s in s if 16*abs(s[0]-4*k)+16*abs(s[1]-16*i)<6*s[2]]:
     continue
    q,a=max(0,i-x//2-2),min(j,i+x//2+3)
    m,r,t=min([(abs(r-4*(i-q)),r,t)for r,t in sp(c[h*q+sz:h*a:h])]
     +[(x,0,0)])
-   if x<6*m:continue
-   sz,z,p=4*k,4*(r+4*q),16*(x+t)//3
+   if x<5*m:continue
+   sz,z,p=4*k,4*(r+4*q),32*(x+t)//5
    if min(sz,z)<p//2 or sz>16*h-p//2-32 or z>16*j-p//2-32:continue
-   n=sum(c[(z+(y*p>>4)+8>>4)*h+(sz+(x*p>>4)+8>>4)]==k for x,y,k in y)
-   if 4*n>=len(y)*3:s+=[(n,sz,z,p)]
+   s+=[(sz,z,p)]
  return s
 def sp(s):
  z,p,n=[0],s[0],0
@@ -92,11 +94,11 @@
   n=s.find(1-p,n)
   if n>0:p,z=1-p,z+[n]
  z+=[len(s)]
- return[(r+z[i+12]+z[i+13]-2,t)for i in range(1+s[0],len(z)-14,2)
-  for r,t in[(z[i]+z[i+1],z[i+12]+z[i+13]-z[i]-z[i+1])]
-  if 23<t and min(z[i]-z[i-1],z[i+14]-z[i+13])*96>=t and max(
-  abs(12*(z[i+y+6]+z[i+y+7]-r)-(y+6)*t)for y in(-5,5,-4,4,-3,3,-2,2)
-  )<=(3*t+144)//10]
+ return[(r+z[i+8]+z[i+9]-2,t)for i in range(1+s[0],len(z)-9,2)
+  for r,t in[(z[i]+z[i+1],z[i+8]+z[i+9]-z[i]-z[i+1])]
+  if 23<t and max(
+  abs(10*(z[i+y-1]+z[i+y]-r)-y*t)for y in(2,8,3,7)
+  )<=(3*t+120)//10]
 def ft(s,x):
  c=[(fr(s,x,y),1-2*(k^s[4]))for x,y,k in u]
  m=n=0
@@ -149,15 +151,15 @@
 def ld():
  c=dd(z.translate(bytes(x<t for t in[min(z[::97])+max(z[::97])>>1]
   for x in range(256))))
- k,k,m,n=max((sum(abs(w(ax(x,y,p,r,t)))for k,x,y,p in c),-abs(r),r,t)
+ k,k,m,n=max((sum(abs(w(ax(x,y,p,r,t)))for x,y,p in c),-abs(r),r,t)
   for r in range(-640,641,64)for t in range(4))
  r=[]
- for k,x,y,p in c:
+ for x,y,p in c:
   s=ax(x,y,p,m,n)
   r+=[s+[int(w(s)<0),(len(r),0,0)]]
  b=e
  for s in r:b=b or a(*f(s),ou,20)
- return(c[0][3]if c else 0,r),b or e
+ return(c[0][2]if c else 0,r),b or e
 e,n,s,t=b'',0,{},'?'
 while n<1:
  r=0
```

### diff: r2reader/reader_lite_v1.py → format-round/reader/reader_v2.py (verbatim)

```diff
--- r2reader/reader_lite_v1.py
+++ format-round/reader/reader_v2.py
@@ -1,3 +1,7 @@
+# reader_v2.py -- the format round's V2 'inverted' reader (2026-10-22,
+# bootstrap/format-round/reader/make_readers.py from the ruled text below;
+# the ring list, the ring check and n dropped; READERS.md = the diff).
+# The ruled text's header follows.
 # reader_lite_v1.py -- the typed stage-2 reader for R2-FORMAT v1 (2026-10-20,
 # the set pass: "Simplify the reader! good enough recovery, not perfect").
 # diet/v1/d06_panel21.py hand-minified (m07; by hand m08, m10-m12, m14;
@@ -52,8 +56,6 @@
  return s^2**32-1
 def fr(s,x,y):
  return s[0]+(s[2][0]*x+s[3][0]*y)//17,s[1]+(s[2][1]*x+s[3][1]*y)//17
-y=[(x,y,sum(x*x+y*y>i*i+i for i in range(7))&1<1)
- for y in range(-7,8)for x in range(-7,8)if x*x+y*y<57]
 i=[(x,y)for y in range(-8,8)for x in range(-8,8)]
 ou=[(x,y)for x,y in i if x*x+y*y>56][:68]
 u=[(x,y,x+y&1)for y in range(-9,9)for x in range(-9,9)
@@ -75,16 +77,15 @@
  for i in range(j):
   for k,x in sp(c[h*i:h*i+h]):
    sz=k+2>>2
-   if[s for s in s if 16*abs(s[1]-4*k)+16*abs(s[2]-16*i)<6*s[3]]:
+   if[s for s in s if 16*abs(s[0]-4*k)+16*abs(s[1]-16*i)<6*s[2]]:
     continue
    q,a=max(0,i-x//2-2),min(j,i+x//2+3)
    m,r,t=min([(abs(r-4*(i-q)),r,t)for r,t in sp(c[h*q+sz:h*a:h])]
     +[(x,0,0)])
-   if x<6*m:continue
-   sz,z,p=4*k,4*(r+4*q),16*(x+t)//3
+   if x<5*m:continue
+   sz,z,p=4*k,4*(r+4*q),32*(x+t)//5
    if min(sz,z)<p//2 or sz>16*h-p//2-32 or z>16*j-p//2-32:continue
-   n=sum(c[(z+(y*p>>4)+8>>4)*h+(sz+(x*p>>4)+8>>4)]==k for x,y,k in y)
-   if 4*n>=len(y)*3:s+=[(n,sz,z,p)]
+   s+=[(sz,z,p)]
  return s
 def sp(s):
  z,p,n=[0],s[0],0
@@ -92,11 +93,11 @@
   n=s.find(1-p,n)
   if n>0:p,z=1-p,z+[n]
  z+=[len(s)]
- return[(r+z[i+12]+z[i+13]-2,t)for i in range(1+s[0],len(z)-14,2)
-  for r,t in[(z[i]+z[i+1],z[i+12]+z[i+13]-z[i]-z[i+1])]
-  if 23<t and min(z[i]-z[i-1],z[i+14]-z[i+13])*96>=t and max(
-  abs(12*(z[i+y+6]+z[i+y+7]-r)-(y+6)*t)for y in(-5,5,-4,4,-3,3,-2,2)
-  )<=(3*t+144)//10]
+ return[(r+z[i+10]+z[i+11]-2,t)for i in range(1+s[0],len(z)-12,2)
+  for r,t in[(z[i]+z[i+1],z[i+10]+z[i+11]-z[i]-z[i+1])]
+  if 23<t and min(z[i]-z[i-1],z[i+12]-z[i+11])*40>=3*t and max(
+  abs(10*(z[i+y]+z[i+y+1]-r)-y*t)for y in(1,9,2,8,3,7)
+  )<=(3*t+120)//10]
 def ft(s,x):
  c=[(fr(s,x,y),1-2*(k^s[4]))for x,y,k in u]
  m=n=0
@@ -149,15 +150,15 @@
 def ld():
  c=dd(z.translate(bytes(x<t for t in[min(z[::97])+max(z[::97])>>1]
   for x in range(256))))
- k,k,m,n=max((sum(abs(w(ax(x,y,p,r,t)))for k,x,y,p in c),-abs(r),r,t)
+ k,k,m,n=max((sum(abs(w(ax(x,y,p,r,t)))for x,y,p in c),-abs(r),r,t)
   for r in range(-640,641,64)for t in range(4))
  r=[]
- for k,x,y,p in c:
+ for x,y,p in c:
   s=ax(x,y,p,m,n)
   r+=[s+[int(w(s)<0),(len(r),0,0)]]
  b=e
  for s in r:b=b or a(*f(s),ou,20)
- return(c[0][3]if c else 0,r),b or e
+ return(c[0][2]if c else 0,r),b or e
 e,n,s,t=b'',0,{},'?'
 while n<1:
  r=0
```

## Search: ruling 32's run, constrained (2026-10-22, machine 1, three runs in parallel at 4 workers)

**The setup.**
- The changeset's `rw/run_search.py`:
  - stage 1's lowercase primer (`build/changeset/stage1/lower/a.py`);
  - orders (0,1,2,3,4,6,8);
  - every line ≤ 72;
  - d, q and k kept out of module scope.
- One change, the impure set. The ruled text already carries the first
  search's spellings, so the main, the walk and the loader are `ld`, `v`
  and `cb` here. Before that search they were `fm`, `wk` and `ld`, the
  keys `run_search.py` looks up, which would raise a KeyError on this
  text.
- `rw_search.py` line 113:
  `imp = {names['ld'], names['v'], names['cb']}`.

**The result.** All three runs ended on the same module-level renames:
- cb → o (the loader);
- i → y (the data list takes the freed name);
- ft → cb;
- a → i;
- o → a (the main loop's output).

| text | start ideal bits / glyphs / lines | phases (bits; rewrite steps) | end ideal / exact bits, glyphs | wall |
|---|---|---|---|---|
| V3 | 12,012.2 / 2,403 / 41 | ren −29.2, rw −13.1 (8), ren −0.8, rw −0.3 (2), ren −1.7, rw −18.4 (12), then none | 11,948.8 / 11,946, **2,390** | 5 min 17 s |
| V1 | 11,812.6 / 2,363 / 40 | ren −33.5, rw −11.8 (9), ren −5.5, rw −14.8 (7), ren −0.2, then none | 11,746.9 / 11,744, **2,349** | 5 min 41 s |
| V2 | 11,940.8 / 2,389 / 40 | ren −42.1, rw −17.6 (13), ren −5.9, then none | 11,875.2 / 11,873, **2,375** | 4 min 21 s |

Logs:
- `build/format-round/reader/search-VARIANT.out`;
- `rw-VARIANT/{search.log,search.json,best_typed.py}`.

The put-back asserts that the typed region of `reader_VARIANT_rw.py` equals
`best_typed.py`.

## Sizes (`size_stage1_v.py`, stage 1's primer, the order tuple (0,1,2,3,4,6,8); `count_reader.py` lines / chars / stripped / longest)

| text | count_reader | lower: typed bytes / glyphs / data lines / **typed total** | upper: glyphs / lines / **typed total** | Δ total vs ruled (lower / upper) |
|---|---|---|---|---|
| ruled `reader_lite_v1.py` | 144 / 3,985 / 3,768 / 69, PASS | 4,140 / 2,495 / 42 / **3,470** | 2,494 / 42 / **3,469** | — |
| `reader_v3.py` | 141 / 3,797 / 3,584 / 69, PASS | 3,949 / 2,402 / 41 / 3,373 | 2,401 / 41 / 3,372 | −97 / −97 |
| **`reader_v3_rw.py`** | 141 / 3,795 / 3,582 / 69, PASS | 3,947 / 2,389 / 40 / **3,356** | 2,389 / 40 / **3,356** | **−114 / −113** |
| `reader_v1.py` | 141 / 3,723 / 3,510 / 69, PASS | 3,875 / 2,363 / 40 / 3,330 | 2,362 / 40 / 3,329 | −140 / −140 |
| **`reader_v1_rw.py`** | 141 / 3,720 / 3,507 / 69, PASS | 3,872 / 2,348 / 40 / **3,315** | 2,348 / 40 / **3,315** | **−155 / −154** |
| `reader_v2.py` | 141 / 3,777 / 3,564 / 69, PASS | 3,929 / 2,388 / 40 / 3,355 | 2,387 / 40 / 3,354 | −115 / −115 |
| **`reader_v2_rw.py`** | 141 / 3,777 / 3,564 / 69, PASS | 3,929 / 2,374 / 40 / **3,341** | 2,373 / 40 / **3,340** | **−129 / −129** |

`size_stage1_v.py` reproduces the ruled text's 3,470 / 3,469.

Not measured: the R2 payload knock-on. The pages of a real chain would be
re-primed by the variant's b.py; §9 of the changeset RESULTS saw +16 B from
a respelling. The stage-1 chain itself was not built for any variant
(`make_typed.py --build`, `e2e.py`).

## Sanity: nominal-b030 seed 1 of the three pages, pooled, each reader on its own variant's set

**The arrangement** (`sanity.py`, the changeset `edge.py` arrangement):
- the text run as `reader.py`;
- N2/B2 from `build/stage1/lower/build.json`;
- the shared d's tuple replaced by (0,1,2,3,4,6,8);
- `build/stage1/lower/b.py` beside it as `b.py`;
- a close compared with `build/bundle/b.py`.

**The inputs.** The page sets are the generator builder's
(`build/format-round/pages/{record,v3,v1,v2}-{coarse,dot}`). All eight
carry the stage-1 lower payload, 15,834 B, sha256 15ee6fc2…, the same as
`build/stage1/lower/r2`. The renders are in
`build/format-round/reader/sanity/renders/`. The record sets are read by
the ruled text, unchanged, as the control.

**Results.** Each frame line reads: seeds printed as "bullseyes", blocks
accepted, chunks held.

| reader | set | p0 | p1 | p2 | close, c.py == bundle |
|---|---|---|---|---|---|
| ruled | record-coarse | 15, 677, 604 | 15, 679, 609 done | — | yes |
| ruled | record-dot | 14, 671, 604 | 14, 673, 609 done | — | yes |
| V3 | v3-coarse | 28, 663, 597 | 30, 658, 609 done | — | yes |
| V3 | v3-dot | 27, 636, 589 | 32, 650, 609 done | — | yes |
| V1 | v1-coarse | 61, 613, 578 | 59, 652, 608 | 51, 668, 609 done | yes |
| V1 | v1-dot | 62, 602, 568 | 59, 651, 608 | 49, 666, 609 done | yes |
| V2 | v2-coarse | 12, 670, 600 | 12, 674, 609 done | — | yes |
| V2 | v2-dot | 6, 658, 606 | 6, 657, 609 done | — | yes |

The searched texts (`reader_v*_rw.py`) printed **identical lines** on all
six variant sets and closed with c.py == bundle.

Walls: 19–40 s per pooled run, at ambient load 5–12, with three or four
runs at a time. They are not paired and not comparable.

**The "15 bullseyes" criterion is NOT met as printed.** The printed count is
the length of the seed list. Per page (`seeds.py`; on a bullseye = within
one module of a bullseye block's centre):

| set | p0: seeds / true bullseyes found (missed) | p1 | p2 |
|---|---|---|---|
| record-coarse (ruled) | 15 / 15 | 15 / 15 | 15 / 15 |
| record-dot (ruled) | 14 / 14 (14,8) | 14 / 14 (14,8) | 14 / 14 (14,8) |
| v3-coarse | 28 / 15 | 30 / 15 | 35 / 15 |
| v3-dot | 27 / 10 (8,11) (14,2) (14,8) (20,5) (26,8) | 32 / 10 (2,2) (2,8) (14,8) (14,14) (26,8) | 35 / 12 (2,2) (14,8) (20,5) |
| v1-coarse | 61 / 15 | 59 / 14 (26,8) | 51 / 15 |
| v1-dot | 62 / 14 (14,8) | 59 / 14 (14,8) | 49 / 14 (14,8) |
| v2-coarse | 12 / 12 (8,17) (20,11) (26,14) | 12 / 12 (same three) | 14 / 12 (same three) |
| v2-dot | 6 / 6 (9 missed) | 6 / 5 (10 missed) | 8 / 6 (9 missed) |

Control, a diagnostic text that is not proposed
(`build/format-round/reader/diag/reader_noring.py`): the ruled text with
only the common edits, so the uniform comb with the quarter-module flank
and no ring check. On record-coarse it gives 266 / 274 / 287 seeds and
14 / 14 / 10 true bullseyes. On v3-coarse p0 it gives 265 seeds. The V3
flank rule therefore cuts the seed list from about 270 to 28–35. The
census is in `build/format-round/reader/diag/seeds-b030.txt`.

**What the census shows** (spm 2, the nominal preset: 2 px per module).
These are measured on single renders; the mechanisms are read off the
thresholded runs (`runs_at.py`) and are not tested further.

- **V3.** All 15 true bullseyes are found on every coarse page; on the
  dot rendering 3–5 are missed per page. There are 13–20 false seeds per
  coarse page.
  - On p0, 10 of the 13 false seeds sit on a timing line or a crossing
    (offset ≈ ±8 modules in x or y from a block centre), 3 in data.
  - In the runs at four of them (`runs_at.py`), the comb's long flank is a
    4–8 px white run. It appears where the image row, tilted by the
    render's perspective, leaves the timing line. Read off the runs, not
    tested.
- **V1.** The true bullseyes are found, except (26,8) on coarse p1 and
  (14,8) on every dot page. Each page has 35–48 false seeds, scattered over
  the data. The nine-run comb with four checked centres and a tolerance of
  0.6 module (at 2 px per module) is loose on random modules.
- **V2.** False seeds per page: 0, 0, 2 on coarse; 0, 1, 2 on dot. True
  bullseyes are missed: 3 per page on coarse, 9–10 on dot.
  - At 2 px per module the white centre module, surrounded by eight ink
    modules (ring 1 at q = 1 and 2), shrinks to 1 px or merges. The
    pattern reads `#2 .1 #3` or `#6`, so the eleven-run count fails.
  - This is a property of the pattern at this sampling, not of the comb.
- **The dot rendering's centre** is a disc of one module diameter. On
  record-dot and v1-dot it drops out at (14,8) on every page: the row
  through the centre reads `.5` where the record reads `#2 .2 #2`.
- **The header.** Every run closed, so the header was read: V3 through
  its own 68-module list, V1 and V2 through the ruled one.

<details><summary>diff: reader_v3.py → reader_v3_rw.py (the search's respelling, verbatim)</summary>

```diff
--- format-round/reader/reader_v3.py
+++ format-round/reader/reader_v3_rw.py
@@ -1,7 +1,12 @@
-# reader_v3.py -- the format round's V3 'axis bits moved, one flank' reader
+# reader_v3_rw.py -- the format round's V3 'axis bits moved, one flank' reader
 # (2026-10-22, bootstrap/format-round/reader/make_readers.py from the ruled
 # text below; the ring list, the ring check and n dropped; READERS.md = the
 # diff).
+# Then ruling 32's rename-and-rewrite search (format-
+# round/reader/run_search_v.py, the changeset's rw/run_search.py under stage
+# 1's a.py) respelled the region: names and equivalent spellings chosen by
+# compressed size, the same program (the ruled text's functions, now: cb o,
+# ft cb, a i; ld, v, be, rb, sp, dd, fr, f, ax, w, b keep their names).
 # The ruled text's header follows.
 # reader_lite_v1.py -- the typed stage-2 reader for R2-FORMAT v1 (2026-10-20,
 # the set pass: "Simplify the reader! good enough recovery, not perfect").
@@ -45,21 +50,19 @@
   h=h<<8|u&255
  return h.to_bytes(m+n,'big')[m:]
 #--- end shared ---
-def cb(c):
+def o(c):
  s=open(c,'rb').read()
  m,n=[int(r)for r in s[:64].split()[1:3]]
  return m,n,s[len(s)-n*m:]
-def b(c):
- s=2**32-1
- for i in c:
-  s=i^s
-  for x in range(8):s=s>>1^3988292384*(s&1)
- return s^2**32-1
+def f(s):
+ sz={(x,y):rb(*fr(s,x,y))for y in range(-9,9)for x in range(-9,9)}
+ z=sorted(sz[x,y]for x,y,k in u)
+ return sz,z[8]+z[59]>>1
+y=[(x,y)for y in range(-8,8)for x in range(-8,8)]
 def fr(s,x,y):
  return s[0]+(s[2][0]*x+s[3][0]*y)//17,s[1]+(s[2][1]*x+s[3][1]*y)//17
-i=[(x,y)for y in range(-8,8)for x in range(-8,8)]
-ou=[(x,y)for x,y in i if x*y and x*x+y*y>56][:68]
-u=[(x,y,x+y&1)for y in range(-9,9)for x in range(-9,9)
+ou=[(x,y)for x,y in y if x*y and x*x+y*y>56][:68]
+u=[(x,y,1&x+y)for y in range(-9,9)for x in range(-9,9)
  if{x,y}&{-9,8}]
 def ax(x,y,p,r,t):
  s=4096-(r*r>>13)
@@ -70,7 +73,7 @@
 def rb(s,x):
  s=min(max(s,0),16*h-17)
  x=min(max(x,0),16*j-17)
- q,p,i=s&15,x&15,(x>>4)*h+(s>>4)
+ q,p,i=s&15,x&15,h*(x>>4)+(s>>4)
  return((z[i]*(16-q)+z[i+1]*q)*(16-p)
   +(z[i+h]*(16-q)+z[i+h+1]*q)*p)//256
 def dd(c):
@@ -78,13 +81,13 @@
  for i in range(j):
   for k,x in sp(c[h*i:h*i+h]):
    sz=k+2>>2
-   if[s for s in s if 16*abs(s[0]-4*k)+16*abs(s[1]-16*i)<6*s[2]]:
+   if[s for s in s if s[2]*6>16*abs(s[0]-4*k)+16*abs(s[1]-16*i)]:
     continue
-   q,a=max(0,i-x//2-2),min(j,i+x//2+3)
-   m,r,t=min([(abs(r-4*(i-q)),r,t)for r,t in sp(c[h*q+sz:h*a:h])]
+   q,n=max(0,i-x//2-2),min(j,i+x//2+3)
+   m,r,t=min([(abs(r-4*(i-q)),r,t)for r,t in sp(c[h*q+sz:h*n:h])]
     +[(x,0,0)])
    if x<6*m:continue
-   sz,z,p=4*k,4*(r+4*q),16*(x+t)//3
+   sz,z,p=k*4,4*(r+4*q),16*(x+t)//3
    if min(sz,z)<p//2 or sz>16*h-p//2-32 or z>16*j-p//2-32:continue
    s+=[(sz,z,p)]
  return s
@@ -96,21 +99,21 @@
  z+=[len(s)]
  return[(r+z[i+12]+z[i+13]-2,t)for i in range(1+s[0],len(z)-14,2)
   for r,t in[(z[i]+z[i+1],z[i+12]+z[i+13]-z[i]-z[i+1])]
-  if 23<t and max(z[i]-z[i-1],z[i+14]-z[i+13])*16>=t and max(
-  abs(12*(z[i+y+6]+z[i+y+7]-r)-(y+6)*t)for y in(-5,5,-4,4,-3,3,-2,2)
+  if t>23 and max(z[i]-z[i-1],z[i+14]-z[i+13])*16>=t and max(
+  abs(12*(z[i+s+6]+z[i+s+7]-r)-(s+6)*t)for s in(-5,5,-4,4,-3,3,-2,2)
   )<=(3*t+144)//10]
-def ft(s,x):
+def w(s):
+ return sum(rb(*fr(s,x,y))*(1-2*k)for x,y,k in u)
+def be(s):
+ z,t=f(s)
+ return i(z,t,y,32)if sum(z[x,y]<t for x,y in y)>3 else b''
+def cb(s,x):
  c=[(fr(s,x,y),1-2*(k^s[4]))for x,y,k in u]
  m=n=0
  for y in(x>>5,x>>6,x>>7,x//256):
   k,k,m,n=max((sum(rb(x+r,y+s)*t for(x,y),t in c),-abs(r-m)-abs(s-n)
    ,r,s)for r in(m-y,m,m+y)for s in(n-y,n,n+y))
  return m,n
-def w(s):
- return sum(rb(*fr(s,x,y))*(1-2*k)for x,y,k in u)
-def be(s):
- r,t=f(s)
- return a(r,t,i,32)if sum(r[x,y]<t for x,y in i)>3 else b''
 def v(p,t):
  z={}
  f,i={},5*p>>4
@@ -123,7 +126,7 @@
   if min(s[0],s[1],16*h-32-s[0],16*j-32-s[1])<5*p>>3:continue
   q,c,b=s[5]
   if c or b:
-   m,n=ft(s,p)
+   m,n=cb(s,p)
    s[0],s[1]=s[0]+m,s[1]+n
    for x,y in((2,b),(3,c)):
     a=(y>0)-(y<0)
@@ -136,20 +139,23 @@
    t+=[[s[0]+y*s[2+x//2][0],s[1]+y*s[2+x//2][1],s[2],s[3],1-s[4],
     (q,c+y*(x>1),b+y*(x<2))]for x in range(4)for y in[1-2*(x&1)]]
  return sz
-def f(s):
- sz={(x,y):rb(*fr(s,x,y))for y in range(-9,9)for x in range(-9,9)}
- z=sorted(sz[x,y]for x,y,k in u)
- return sz,z[8]+z[59]>>1
-def a(z,x,y,p):
- m=len(y)
- i=int(''.join('01'[x-z[i,k]+(z[i-1,k]+z[i+1,k]+z[i,k-1]+z[i,k+1]
-  -4*z[i,k]>>1)>0]for i,k in y),2)
- for t in[0]+[1<<t for t in range(m*(p>20))]:
+def b(c):
+ s=2**32-1
+ for i in c:
+  s=i^s
+  for x in range(8):s=s%2*3988292384^s>>1
+ return s^2**32-1
+def i(z,q,c,p):
+ a=len(c)
+ i=int(''.join('01'[q-z[i,k]+(z[i-1,k]+z[i+1,k]+z[i,k-1]+z[i,k+1]
+  -z[i,k]*4>>1)>0]for i,k in c),2)
+ for t in[0]+[1<<t for t in range(a*(p>20))]:
   s=i^t
-  if b(e+(s>>p).to_bytes((m-p)//8,'big'))%2**p==s%2**p:
-   return(s>>p).to_bytes((m-p)//8,'big')
+  if b(e+(s>>p).to_bytes((a-p)//8,'big'))%2**p==s%2**p:
+   return(s>>p).to_bytes((a-p)//8,'big')
+e,n,s,t=b'',0,{},'?'
 def ld():
- c=dd(z.translate(bytes(x<t for t in[min(z[::97])+max(z[::97])>>1]
+ c=dd(z.translate(bytes(x<t for t in[(min(z[::97])+max(z[::97]))//2]
   for x in range(256))))
  k,k,m,n=max((sum(abs(w(ax(x,y,p,r,t)))for x,y,p in c),-abs(r),r,t)
   for r in range(-640,641,64)for t in range(4))
@@ -158,14 +164,13 @@
   s=ax(x,y,p,m,n)
   r+=[s+[int(w(s)<0),(len(r),0,0)]]
  b=e
- for s in r:b=b or a(*f(s),ou,20)
+ for s in r:b=b or i(*f(s),ou,20)
  return(c[0][2]if c else 0,r),b or e
-e,n,s,t=b'',0,{},'?'
 while n<1:
  r=0
  try:
   r=input('file: ').strip()
-  h,j,z=cb(r)
+  h,j,z=o(r)
   c,e=ld()
   m='%d bullseyes'%len(c[1])
   p=v(*c)if e else[]
@@ -183,7 +188,7 @@
  print(r+':',m+',',len(p),'blocks accepted, chunks',len(s),'/',t,
   ['more','done'][n])
 if n:
- o=d(int.from_bytes(g,'big'),N2,open('b.py','rb').read())
- assert b(o)==B2
- open('c.py','wb').write(o)
+ a=d(int.from_bytes(g,'big'),N2,open('b.py','rb').read())
+ assert b(a)==B2
+ open('c.py','wb').write(a)
 # END READER
```

</details>

<details><summary>diff: reader_v1.py → reader_v1_rw.py (the search's respelling, verbatim)</summary>

```diff
--- format-round/reader/reader_v1.py
+++ format-round/reader/reader_v1_rw.py
@@ -1,7 +1,12 @@
-# reader_v1.py -- the format round's V1 'the 3-wide band' reader
+# reader_v1_rw.py -- the format round's V1 'the 3-wide band' reader
 # (2026-10-22, bootstrap/format-round/reader/make_readers.py from the ruled
 # text below; the ring list, the ring check and n dropped; READERS.md = the
 # diff).
+# Then ruling 32's rename-and-rewrite search (format-
+# round/reader/run_search_v.py, the changeset's rw/run_search.py under stage
+# 1's a.py) respelled the region: names and equivalent spellings chosen by
+# compressed size, the same program (the ruled text's functions, now: cb o,
+# ft cb, a i; ld, v, be, rb, sp, dd, fr, f, ax, w, b keep their names).
 # The ruled text's header follows.
 # reader_lite_v1.py -- the typed stage-2 reader for R2-FORMAT v1 (2026-10-20,
 # the set pass: "Simplify the reader! good enough recovery, not perfect").
@@ -45,7 +50,7 @@
   h=h<<8|u&255
  return h.to_bytes(m+n,'big')[m:]
 #--- end shared ---
-def cb(c):
+def o(c):
  s=open(c,'rb').read()
  m,n=[int(r)for r in s[:64].split()[1:3]]
  return m,n,s[len(s)-n*m:]
@@ -53,12 +58,16 @@
  s=2**32-1
  for i in c:
   s=i^s
-  for x in range(8):s=s>>1^3988292384*(s&1)
+  for x in range(8):s=3988292384*(s&1)^s>>1
  return s^2**32-1
+y=[(x,y)for y in range(-8,8)for x in range(-8,8)]
 def fr(s,x,y):
  return s[0]+(s[2][0]*x+s[3][0]*y)//17,s[1]+(s[2][1]*x+s[3][1]*y)//17
-i=[(x,y)for y in range(-8,8)for x in range(-8,8)]
-ou=[(x,y)for x,y in i if x*x+y*y>56][:68]
+ou=[(x,y)for x,y in y if x*x+y*y>56][:68]
+def f(s):
+ r={(x,y):rb(*fr(s,x,y))for y in range(-9,9)for x in range(-9,9)}
+ z=sorted(r[x,y]for x,y,k in u)
+ return r,z[8]+z[59]>>1
 u=[(x,y,x+y&1)for y in range(-9,9)for x in range(-9,9)
  if{x,y}&{-9,8}]
 def ax(x,y,p,r,t):
@@ -70,21 +79,21 @@
 def rb(s,x):
  s=min(max(s,0),16*h-17)
  x=min(max(x,0),16*j-17)
- q,p,i=s&15,x&15,(x>>4)*h+(s>>4)
- return((z[i]*(16-q)+z[i+1]*q)*(16-p)
-  +(z[i+h]*(16-q)+z[i+h+1]*q)*p)//256
+ q,y,i=s&15,x&15,h*(x>>4)+(s>>4)
+ return((16-y)*(z[i]*(16-q)+z[i+1]*q)
+  +y*(z[i+h]*(16-q)+z[i+h+1]*q))//256
 def dd(c):
  s=[]
  for i in range(j):
-  for k,x in sp(c[h*i:h*i+h]):
-   sz=k+2>>2
-   if[s for s in s if 16*abs(s[0]-4*k)+16*abs(s[1]-16*i)<6*s[2]]:
+  for y,x in sp(c[h*i:h*i+h]):
+   sz=y+2>>2
+   if[s for s in s if 16*abs(s[0]-4*y)+16*abs(s[1]-16*i)<6*s[2]]:
     continue
-   q,a=max(0,i-x//2-2),min(j,i+x//2+3)
-   m,r,t=min([(abs(r-4*(i-q)),r,t)for r,t in sp(c[h*q+sz:h*a:h])]
+   q,n=max(0,i-x//2-2),min(j,i+x//2+3)
+   m,r,t=min([(abs(r-4*(i-q)),r,t)for r,t in sp(c[h*q+sz:h*n:h])]
     +[(x,0,0)])
    if x<5*m:continue
-   sz,z,p=4*k,4*(r+4*q),32*(x+t)//5
+   sz,p,z=4*y,32*(x+t)//5,4*(r+4*q)
    if min(sz,z)<p//2 or sz>16*h-p//2-32 or z>16*j-p//2-32:continue
    s+=[(sz,z,p)]
  return s
@@ -96,21 +105,22 @@
  z+=[len(s)]
  return[(r+z[i+8]+z[i+9]-2,t)for i in range(1+s[0],len(z)-9,2)
   for r,t in[(z[i]+z[i+1],z[i+8]+z[i+9]-z[i]-z[i+1])]
-  if 23<t and max(
-  abs(10*(z[i+y-1]+z[i+y]-r)-y*t)for y in(2,8,3,7)
-  )<=(3*t+120)//10]
-def ft(s,x):
+  if t>23 and (3*t+120)//10>=max(
+  abs(10*(z[i+h-1]+z[i+h]-r)-h*t)for h in(2,8,3,7)
+  )]
+def w(s):
+ return sum(rb(*fr(s,x,y))*(1-2*k)for x,y,k in u)
+def cb(s,x):
  c=[(fr(s,x,y),1-2*(k^s[4]))for x,y,k in u]
  m=n=0
  for y in(x>>5,x>>6,x>>7,x//256):
   k,k,m,n=max((sum(rb(x+r,y+s)*t for(x,y),t in c),-abs(r-m)-abs(s-n)
    ,r,s)for r in(m-y,m,m+y)for s in(n-y,n,n+y))
  return m,n
-def w(s):
- return sum(rb(*fr(s,x,y))*(1-2*k)for x,y,k in u)
 def be(s):
  r,t=f(s)
- return a(r,t,i,32)if sum(r[x,y]<t for x,y in i)>3 else b''
+ return i(r,t,y,32)if sum(r[x,y]<t for x,y in y)>3 else b''
+e,n,s,t=b'',0,{},'?'
 def v(p,t):
  z={}
  f,i={},5*p>>4
@@ -123,7 +133,7 @@
   if min(s[0],s[1],16*h-32-s[0],16*j-32-s[1])<5*p>>3:continue
   q,c,b=s[5]
   if c or b:
-   m,n=ft(s,p)
+   m,n=cb(s,p)
    s[0],s[1]=s[0]+m,s[1]+n
    for x,y in((2,b),(3,c)):
     a=(y>0)-(y<0)
@@ -136,20 +146,16 @@
    t+=[[s[0]+y*s[2+x//2][0],s[1]+y*s[2+x//2][1],s[2],s[3],1-s[4],
     (q,c+y*(x>1),b+y*(x<2))]for x in range(4)for y in[1-2*(x&1)]]
  return sz
-def f(s):
- sz={(x,y):rb(*fr(s,x,y))for y in range(-9,9)for x in range(-9,9)}
- z=sorted(sz[x,y]for x,y,k in u)
- return sz,z[8]+z[59]>>1
-def a(z,x,y,p):
- m=len(y)
- i=int(''.join('01'[x-z[i,k]+(z[i-1,k]+z[i+1,k]+z[i,k-1]+z[i,k+1]
-  -4*z[i,k]>>1)>0]for i,k in y),2)
- for t in[0]+[1<<t for t in range(m*(p>20))]:
+def i(z,q,c,y):
+ m=len(c)
+ i=int(''.join('01'[q-z[i,k]+(z[i-1,k]+z[i+1,k]+z[i,k-1]+z[i,k+1]
+  -4*z[i,k]>>1)>0]for i,k in c),2)
+ for t in[0]+[1<<t for t in range(m*(y>20))]:
   s=i^t
-  if b(e+(s>>p).to_bytes((m-p)//8,'big'))%2**p==s%2**p:
-   return(s>>p).to_bytes((m-p)//8,'big')
+  if s%2**y==b(e+(s>>y).to_bytes((m-y)//8,'big'))%2**y:
+   return(s>>y).to_bytes((m-y)//8,'big')
 def ld():
- c=dd(z.translate(bytes(x<t for t in[min(z[::97])+max(z[::97])>>1]
+ c=dd(z.translate(bytes(x<t for t in[(min(z[::97])+max(z[::97]))//2]
   for x in range(256))))
  k,k,m,n=max((sum(abs(w(ax(x,y,p,r,t)))for x,y,p in c),-abs(r),r,t)
   for r in range(-640,641,64)for t in range(4))
@@ -158,14 +164,13 @@
   s=ax(x,y,p,m,n)
   r+=[s+[int(w(s)<0),(len(r),0,0)]]
  b=e
- for s in r:b=b or a(*f(s),ou,20)
+ for s in r:b=b or i(*f(s),ou,20)
  return(c[0][2]if c else 0,r),b or e
-e,n,s,t=b'',0,{},'?'
 while n<1:
  r=0
  try:
   r=input('file: ').strip()
-  h,j,z=cb(r)
+  h,j,z=o(r)
   c,e=ld()
   m='%d bullseyes'%len(c[1])
   p=v(*c)if e else[]
@@ -177,13 +182,13 @@
  if e:
   sz=int.from_bytes(e[:2],'big')
   t=(sz+25)//26
-  if sum(x in s for x in range(t))==t:
+  if t==sum(x in s for x in range(t)):
    g=b''.join(s[x]for x in range(t))[:sz]
    n=b(g)==int.from_bytes(e[2:],'big')
  print(r+':',m+',',len(p),'blocks accepted, chunks',len(s),'/',t,
   ['more','done'][n])
 if n:
- o=d(int.from_bytes(g,'big'),N2,open('b.py','rb').read())
- assert b(o)==B2
- open('c.py','wb').write(o)
+ a=d(int.from_bytes(g,'big'),N2,open('b.py','rb').read())
+ assert b(a)==B2
+ open('c.py','wb').write(a)
 # END READER
```

</details>

<details><summary>diff: reader_v2.py → reader_v2_rw.py (the search's respelling, verbatim)</summary>

```diff
--- format-round/reader/reader_v2.py
+++ format-round/reader/reader_v2_rw.py
@@ -1,6 +1,11 @@
-# reader_v2.py -- the format round's V2 'inverted' reader (2026-10-22,
+# reader_v2_rw.py -- the format round's V2 'inverted' reader (2026-10-22,
 # bootstrap/format-round/reader/make_readers.py from the ruled text below;
 # the ring list, the ring check and n dropped; READERS.md = the diff).
+# Then ruling 32's rename-and-rewrite search (format-
+# round/reader/run_search_v.py, the changeset's rw/run_search.py under stage
+# 1's a.py) respelled the region: names and equivalent spellings chosen by
+# compressed size, the same program (the ruled text's functions, now: cb o,
+# ft cb, a i; ld, v, be, rb, sp, dd, fr, f, ax, w, b keep their names).
 # The ruled text's header follows.
 # reader_lite_v1.py -- the typed stage-2 reader for R2-FORMAT v1 (2026-10-20,
 # the set pass: "Simplify the reader! good enough recovery, not perfect").
@@ -44,7 +49,7 @@
   h=h<<8|u&255
  return h.to_bytes(m+n,'big')[m:]
 #--- end shared ---
-def cb(c):
+def o(c):
  s=open(c,'rb').read()
  m,n=[int(r)for r in s[:64].split()[1:3]]
  return m,n,s[len(s)-n*m:]
@@ -52,12 +57,12 @@
  s=2**32-1
  for i in c:
   s=i^s
-  for x in range(8):s=s>>1^3988292384*(s&1)
+  for x in range(8):s=3988292384*(s&1)^s>>1
  return s^2**32-1
+y=[(x,y)for y in range(-8,8)for x in range(-8,8)]
 def fr(s,x,y):
  return s[0]+(s[2][0]*x+s[3][0]*y)//17,s[1]+(s[2][1]*x+s[3][1]*y)//17
-i=[(x,y)for y in range(-8,8)for x in range(-8,8)]
-ou=[(x,y)for x,y in i if x*x+y*y>56][:68]
+ou=[(x,y)for x,y in y if x*x+y*y>56][:68]
 u=[(x,y,x+y&1)for y in range(-9,9)for x in range(-9,9)
  if{x,y}&{-9,8}]
 def ax(x,y,p,r,t):
@@ -69,21 +74,21 @@
 def rb(s,x):
  s=min(max(s,0),16*h-17)
  x=min(max(x,0),16*j-17)
- q,p,i=s&15,x&15,(x>>4)*h+(s>>4)
- return((z[i]*(16-q)+z[i+1]*q)*(16-p)
-  +(z[i+h]*(16-q)+z[i+h+1]*q)*p)//256
+ q,y,i=s&15,x&15,h*(x>>4)+(s>>4)
+ return((z[i]*(16-q)+z[i+1]*q)*(16-y)
+  +(z[i+h]*(16-q)+z[i+h+1]*q)*y)//256
 def dd(c):
  s=[]
  for i in range(j):
-  for k,x in sp(c[h*i:h*i+h]):
-   sz=k+2>>2
-   if[s for s in s if 16*abs(s[0]-4*k)+16*abs(s[1]-16*i)<6*s[2]]:
+  for y,x in sp(c[h*i:h*i+h]):
+   sz=y+2>>2
+   if[s for s in s if s[2]*6>16*abs(s[0]-4*y)+16*abs(s[1]-16*i)]:
     continue
-   q,a=max(0,i-x//2-2),min(j,i+x//2+3)
-   m,r,t=min([(abs(r-4*(i-q)),r,t)for r,t in sp(c[h*q+sz:h*a:h])]
+   q,n=max(0,i-x//2-2),min(j,i+x//2+3)
+   m,r,t=min([(abs(r-4*(i-q)),r,t)for r,t in sp(c[h*q+sz:h*n:h])]
     +[(x,0,0)])
    if x<5*m:continue
-   sz,z,p=4*k,4*(r+4*q),32*(x+t)//5
+   sz,p,z=4*y,32*(x+t)//5,4*(r+4*q)
    if min(sz,z)<p//2 or sz>16*h-p//2-32 or z>16*j-p//2-32:continue
    s+=[(sz,z,p)]
  return s
@@ -95,10 +100,10 @@
  z+=[len(s)]
  return[(r+z[i+10]+z[i+11]-2,t)for i in range(1+s[0],len(z)-12,2)
   for r,t in[(z[i]+z[i+1],z[i+10]+z[i+11]-z[i]-z[i+1])]
-  if 23<t and min(z[i]-z[i-1],z[i+12]-z[i+11])*40>=3*t and max(
-  abs(10*(z[i+y]+z[i+y+1]-r)-y*t)for y in(1,9,2,8,3,7)
+  if t>23 and min(z[i]-z[i-1],z[i+12]-z[i+11])*40>=3*t and max(
+  abs((z[i+h]+z[i+h+1]-r)*10-h*t)for h in(1,9,2,8,3,7)
   )<=(3*t+120)//10]
-def ft(s,x):
+def cb(s,x):
  c=[(fr(s,x,y),1-2*(k^s[4]))for x,y,k in u]
  m=n=0
  for y in(x>>5,x>>6,x>>7,x//256):
@@ -109,7 +114,7 @@
  return sum(rb(*fr(s,x,y))*(1-2*k)for x,y,k in u)
 def be(s):
  r,t=f(s)
- return a(r,t,i,32)if sum(r[x,y]<t for x,y in i)>3 else b''
+ return i(r,t,y,32)if sum(r[x,y]<t for x,y in y)>3 else b''
 def v(p,t):
  z={}
  f,i={},5*p>>4
@@ -122,7 +127,7 @@
   if min(s[0],s[1],16*h-32-s[0],16*j-32-s[1])<5*p>>3:continue
   q,c,b=s[5]
   if c or b:
-   m,n=ft(s,p)
+   m,n=cb(s,p)
    s[0],s[1]=s[0]+m,s[1]+n
    for x,y in((2,b),(3,c)):
     a=(y>0)-(y<0)
@@ -139,32 +144,32 @@
  sz={(x,y):rb(*fr(s,x,y))for y in range(-9,9)for x in range(-9,9)}
  z=sorted(sz[x,y]for x,y,k in u)
  return sz,z[8]+z[59]>>1
-def a(z,x,y,p):
- m=len(y)
- i=int(''.join('01'[x-z[i,k]+(z[i-1,k]+z[i+1,k]+z[i,k-1]+z[i,k+1]
-  -4*z[i,k]>>1)>0]for i,k in y),2)
- for t in[0]+[1<<t for t in range(m*(p>20))]:
+e,n,s,t=b'',0,{},'?'
+def i(z,r,c,y):
+ m=len(c)
+ i=int(''.join('01'[r-z[i,k]+(z[i-1,k]+z[i+1,k]+z[i,k-1]+z[i,k+1]
+  -4*z[i,k]>>1)>0]for i,k in c),2)
+ for t in[0]+[1<<t for t in range(m*(y>20))]:
   s=i^t
-  if b(e+(s>>p).to_bytes((m-p)//8,'big'))%2**p==s%2**p:
-   return(s>>p).to_bytes((m-p)//8,'big')
+  if s%2**y==b(e+(s>>y).to_bytes((m-y)//8,'big'))%2**y:
+   return(s>>y).to_bytes((m-y)//8,'big')
 def ld():
- c=dd(z.translate(bytes(x<t for t in[min(z[::97])+max(z[::97])>>1]
+ c=dd(z.translate(bytes(x<t for t in[(min(z[::97])+max(z[::97]))//2]
   for x in range(256))))
  k,k,m,n=max((sum(abs(w(ax(x,y,p,r,t)))for x,y,p in c),-abs(r),r,t)
   for r in range(-640,641,64)for t in range(4))
- r=[]
+ t=[]
  for x,y,p in c:
   s=ax(x,y,p,m,n)
-  r+=[s+[int(w(s)<0),(len(r),0,0)]]
+  t+=[s+[int(w(s)<0),(len(t),0,0)]]
  b=e
- for s in r:b=b or a(*f(s),ou,20)
- return(c[0][2]if c else 0,r),b or e
-e,n,s,t=b'',0,{},'?'
+ for s in t:b=b or i(*f(s),ou,20)
+ return(c[0][2]if c else 0,t),b or e
 while n<1:
  r=0
  try:
   r=input('file: ').strip()
-  h,j,z=cb(r)
+  h,j,z=o(r)
   c,e=ld()
   m='%d bullseyes'%len(c[1])
   p=v(*c)if e else[]
@@ -176,13 +181,13 @@
  if e:
   sz=int.from_bytes(e[:2],'big')
   t=(sz+25)//26
-  if sum(x in s for x in range(t))==t:
+  if t==sum(x in s for x in range(t)):
    g=b''.join(s[x]for x in range(t))[:sz]
    n=b(g)==int.from_bytes(e[2:],'big')
  print(r+':',m+',',len(p),'blocks accepted, chunks',len(s),'/',t,
   ['more','done'][n])
 if n:
- o=d(int.from_bytes(g,'big'),N2,open('b.py','rb').read())
- assert b(o)==B2
- open('c.py','wb').write(o)
+ a=d(int.from_bytes(g,'big'),N2,open('b.py','rb').read())
+ assert b(a)==B2
+ open('c.py','wb').write(a)
 # END READER
```

</details>

## Not run

- the acceptance sets (`run_sets` over `w4_sets`, which need their own
  renders per variant), the envelope edge and the sigma 0.45 quarters
  (`edge_*.py`), the one-bullseye cases (`one_bull.py`): the measurer's;
- the stage-1 chain (`make_typed.py --build`, `stage1/e2e.py`) and the R2
  payload re-priming for any variant;
- paired walls;
- the four phone photos (format of record; cannot test a variant);
- any reader-side mitigation of the false seeds (V3, V1) or the missed V2
  centres. The texts follow the brief exactly; tightening the comb (all
  interior runs checked, a narrower tolerance) is an open lever, not
  measured;
- slow lanes, prints, scans.
