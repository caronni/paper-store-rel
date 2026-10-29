# reader_lite_v1.py -- the typed stage-2 reader for R2-FORMAT v1 (2026-10-20,
# the set pass: "Simplify the reader! good enough recovery, not perfect").
# diet/v1/d06_panel21.py hand-minified (m07; by hand m08, m10-m12, m14;
# names by diet/w4_names.py at m09); the record: diet/LADDER-2026-10-20.md.
# The 2026-10-22 change set (the owner's rulings on ideation/IDEAS-2026-10-22.md
# and axes/JUDGE-2026-10-22.md; edits changeset/apply.py, the record
# changeset/RESULTS-2026-10-22.md; the print of record's text is git
# b544669e): the stage names of ruling 34 (the primer read from b.py, the
# output written as c.py); the quarter turn folded into ax and the ring by
# the parity of the rounded radius; the frame check on the block centre; the
# walk passes a block whose CRC checks or that is white (the timing test
# gone); the prompt 'file: '; the 0/1 text grid no longer read (the Plate's
# one-liner, r2reader/grid_to_pgm.py, writes the PGM); a score tie in ft
# broken toward the nearest offset, in fm toward the smallest rotation.
# Then ruling 32's rename-and-rewrite search (changeset/rw/run_search.py,
# the cloud session's encoder lab re-run under stage 1's a.py) respelled
# the region: names and equivalent spellings chosen by compressed size,
# the same program (fm above is now ld, wk v, rb be, ld cb, v rb, cb sp,
# be dd, sp fr; ft keeps its name; changeset/RESULTS-2026-10-22.md).
# The 2026-10-22 fresh-eyes arms (rulings 53-54; changeset/apply_comp.py,
# changeset/RESULTS-2026-10-22.md sections 16-17): ft scores a shifted copy
# of the pose through w and adds the best offset into the pose in place
# (the same reads, call for call); int.from_bytes and to_bytes take their
# default byte order, so the reader needs Python 3.11 or later (ruling 53,
# the chain's floor); the progress line says 'blocks, chunks'.  The search
# re-run on that text (changeset/run_search_comp.py) renamed about 20
# local names (no module-level name moved) and rewrote four spots: move
# sp 10->11, move w 12->10, flip@137:5, comm@42:10.
# The 2026-10-22 progress line (ruling 56 as amended;
# changeset/apply_prog.py, changeset/RESULTS-2026-10-22.md section 18): per
# file `9@ 500/557`, the seeds found, '@' as the target mark, then the
# chunks held / the header's total ('?' before a header); no file name (the
# prompt line shows it), no blocks count, no done flag (the exit with c.py
# written is the done signal); `cannot read` alone for a file that fails.
# The '@' was printed as %c of 64, since count_reader.py refused the
# character on a typed line.  The chunk store, the done check and the line
# moved inside the try, so the except prints 'cannot read' and nothing else
# (the same reads).  The search re-run on that text
# (changeset/run_search_prog.py) respelled fr p, ft fr, be ft, ld be (so ft
# above is now fr, be ft, ld be); its rewrites: flip@132:6, comm@42:10.
# The literal '@' (the owner's ruling of 2026-10-23, "yes, b.py may include
# the literal @"; changeset/apply_at.py, changeset/RESULTS-2026-10-22.md
# section 19): count_reader.py admits an '@' inside a string literal (the
# ban stays for the operator and decorators, and for ';' and '~'), so the
# line is spelled '%d@ %d/%s'%(m,len(s),t), the same bytes printed.  The
# search re-run on that text (changeset/run_search_at.py) moved no name and
# found one rewrite, comm@42:10 (k*4 for 4*k, -0.09 ideal bits), which
# stage 1's packer prices one glyph more in the lower case; it is not
# taken.
# The grey padding (the owner's ruling of 2026-10-23, "sounds completely
# beneficial ... apply the change with all consequences"; measured as an
# arm in changeset/RESULTS-2026-10-22.md section 19, applied in section 20
# by changeset/apply_pad.py): rb's two clamp lines are gone and cb appends
# one image's worth of mid-grey to the pixels, r*bytes([128])*m.  No sample
# can leave the buffer: a sample left or right of the frame reads the
# adjacent row, one past the bottom reads the padding, one above the top
# wraps (a negative index) to the buffer's end and reads the padding; and
# every sample comes from a bullseye found in the frame or a block the walk
# keeps 10 modules inside it, so an overrun is shorter than the padding
# (the deepest measured, about 12 rows, on a 104 x 104 crop).  And 128
# moves neither extreme of the finder's threshold
# min(z[::97])+max(z[::97])>>1, which samples the padding too, on a frame
# that holds a value at or below 128 and one at or above it: the threshold
# byte-identical on all 328 frames measured.  The search re-run on that
# text (changeset/run_search_at.py --arm pad128) moved cb to stand before
# be and w before dd, respelled ax's step g c and cb's field r t, and took
# 4*k in dd (comm@38:10).
# The convergence of the three searches (ruling 60 of 2026-10-23;
# bootstrap/CONVERGENCE-2026-10-23.md, changeset/run_search_cv.py): the
# search re-run under the chain's own primer, the uppercase a.py of a
# stage-1 build with c.py as the content, at that build's tuple
# (0,1,2,3,4,6) (the earlier runs: the lowercase a.py of the stand-in build
# at (0,1,2,3,4,6,8)).  Round 1 moved cb and fr to the top, f after ax and
# v before sp and ft, respelled ax's step c sz, sp's bit y sz, ft's grey r
# z and v's placed f p, and took two tuple orders in dd and one in v; round
# 2, under round 1's a.py, respelled the pitch p r in fr, rb and a, and
# took (x+t)*16 in dd, r>>8 in fr and >>8 for //256 in rb (shift), t>23 in
# sp (flip); no module-level name moved; round 3's winner (one glyph fewer
# in the upper case, one more in the lower) is not taken.  Each round
# identical call for call on the 129 captures.
# Only the region between the READER markers is typed, minus the shared
# block (the loader's d, here so the file runs on its own).  Run: python3
# reader_lite_v1.py beside b.py (the primer), one P5 PGM frame per line, an
# empty line or the end of input stops; each file is answered with the
# line N@ H/T, a file that cannot be read with 'cannot read', and skipped.
# BEGIN READER
#--- shared with the loader (not typed) ---
def d(x,n,r):
 z=[256**q-1 for q in(0,1,2,3,4,6,8,12,16)]
 m,t,h=len(r),{},0
 for i in range(m+n):
  u=1
  for j in range(8):
   g=[t.setdefault((h&q,u),[0,0])for q in z]
   p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
   s=sum(p)
   if i<m:y=r[i]>>7-j&1
   else:o=x%s;y=o>=p[0];x=x//s*p[y]+o-p[0]*y
   for c in g:c[y],c[1-y]=c[y]+1,min(c[1-y],c[1-y]//4+2)
   u=2*u+y
  h=h<<8|u&255
 return h.to_bytes(m+n,'big')[m:]
#--- end shared ---
def cb(c):
 s=open(c,'rb').read()
 m,r=[int(t)for t in s[:64].split()[1:3]]
 return m,r,s[len(s)-r*m:]+r*bytes([128])*m
def fr(s,r):
 m=n=0
 for y in(r>>5,r>>6,r>>7,r>>8):
  k,k,m,n=max((w([s[0]+r,s[1]+t]+s[2:])*(1-2*s[4]),-abs(r-m)-abs(t-n)
   ,r,t)for r in(m-y,m,m+y)for t in(n-y,n,n+y))
 s[0]+=m
 s[1]+=n
def b(c):
 s=2**32-1
 for i in c:
  s=i^s
  for x in range(8):s=s>>1^3988292384*(s&1)
 return s^2**32-1
def p(s,x,y):
 return s[0]+(s[2][0]*x+s[3][0]*y)//17,s[1]+(s[2][1]*x+s[3][1]*y)//17
y=[(x,y,sum(x*x+y*y>i*i+i for i in range(7))&1<1)
 for y in range(-7,8)for x in range(-7,8)if x*x+y*y<57]
i=[(x,y)for y in range(-8,8)for x in range(-8,8)]
ou=[(x,y)for x,y in i if x*x+y*y>56][:68]
u=[(x,y,x+y&1)for y in range(-9,9)for x in range(-9,9)
 if{x,y}&{-9,8}]
def ax(x,y,p,r,t):
 s=4096-(r*r>>13)
 sz=[17*p*s>>16,17*p*r>>16]
 z=[-17*p*r>>16,17*p*s>>16]
 for i in range(t):sz,z=z,[-sz[0],-sz[1]]
 return[x,y,sz,z]
def f(s):
 sz={(x,y):rb(*p(s,x,y))for y in range(-9,9)for x in range(-9,9)}
 z=sorted(sz[x,y]for x,y,k in u)
 return sz,z[8]+z[59]>>1
def rb(s,r):
 q,c,i=s&15,r&15,(r>>4)*h+(s>>4)
 return((z[i]*(16-q)+z[i+1]*q)*(16-c)
  +(z[i+h]*(16-q)+z[i+h+1]*q)*c)>>8
def w(s):
 return sum(rb(*p(s,x,y))*(1-2*k)for x,y,k in u)
def dd(c):
 s=[]
 for i in range(j):
  for k,x in sp(c[h*i:h*i+h]):
   sz=k+2>>2
   if[s for s in s if 16*abs(s[1]-4*k)+16*abs(s[2]-16*i)<6*s[3]]:
    continue
   q,a=max(0,i-x//2-2),min(j,i+x//2+3)
   m,r,t=min([(abs(r-4*(i-q)),r,t)for r,t in sp(c[h*q+sz:h*a:h])]
    +[(x,0,0)])
   if x<6*m:continue
   p,sz,z=(x+t)*16//3,4*k,4*(r+4*q)
   if min(sz,z)<p//2 or sz>16*h-p//2-32 or z>16*j-p//2-32:continue
   n=sum(c[(z+(y*p>>4)+8>>4)*h+(sz+(x*p>>4)+8>>4)]==k for x,y,k in y)
   if 4*n>=len(y)*3:s+=[(n,sz,z,p)]
 return s
def v(r,t):
 z={}
 a,p=5*r>>4,{}
 sz=[]
 for s in t:
  n=s[0]//a
  k=s[1]//a
  if(n,k)in z:continue
  z[n,k]=1
  if min(s[0],s[1],16*h-32-s[0],16*j-32-s[1])<5*r>>3:continue
  q,c,i=s[5]
  if c or i:
   fr(s,r)
   for x,y in((2,i),(3,c)):
    m=(y>0)-(y<0)
    g=p.get((q,c-m*(x>2),i-m*(x<3)))
    if g and m:s[x]=[m*(s[0]-g[0]),m*(s[1]-g[1])]
  n=(c or i)and ft(s)
  if n:sz+=[n]
  if n!=None:
   p[q,c,i]=s
   t+=[[s[0]+y*s[2+x//2][0],s[1]+y*s[2+x//2][1],s[2],s[3],1-s[4],
    (q,c+y*(x>1),i+y*(x<2))]for x in range(4)for y in[1-2*(x&1)]]
 return sz
def sp(s):
 z,sz,n=[0],s[0],0
 while n>=0:
  n=s.find(1-sz,n)
  if n>0:sz,z=1-sz,z+[n]
 z+=[len(s)]
 return[(r+z[i+12]+z[i+13]-2,t)for i in range(1+s[0],len(z)-14,2)
  for r,t in[(z[i]+z[i+1],z[i+12]+z[i+13]-z[i]-z[i+1])]
  if t>23 and min(z[i]-z[i-1],z[i+14]-z[i+13])*96>=t and max(
  abs(12*(z[i+y+6]+z[i+y+7]-r)-(y+6)*t)for y in(-5,5,-4,4,-3,3,-2,2)
  )<=(3*t+144)//10]
def ft(s):
 z,t=f(s)
 return a(z,t,i,32)if sum(z[x,y]<t for x,y in i)>3 else b''
def a(z,x,y,r):
 m=len(y)
 i=int(''.join('01'[x-z[i,k]+(z[i-1,k]+z[i+1,k]+z[i,k-1]+z[i,k+1]
  -4*z[i,k]>>1)>0]for i,k in y),2)
 for t in[0]+[1<<t for t in range(m*(r>20))]:
  s=i^t
  if b(e+(s>>r).to_bytes((m-r)//8))%2**r==s%2**r:
   return(s>>r).to_bytes((m-r)//8)
def be():
 c=dd(z.translate(bytes(x<t for t in[min(z[::97])+max(z[::97])>>1]
  for x in range(256))))
 k,k,m,n=max((sum(abs(w(ax(x,y,p,r,t)))for k,x,y,p in c),-abs(r),r,t)
  for r in range(-640,641,64)for t in range(4))
 r=[]
 for k,x,y,p in c:
  s=ax(x,y,p,m,n)
  r+=[s+[int(w(s)<0),(len(r),0,0)]]
 t=e
 for s in r:t=t or a(*f(s),ou,20)
 return(c[0][3]if c else 0,r),t or e
e,n,s,t=b'',0,{},'?'
while n<1:
 r=0
 try:
  r=input('file: ').strip()
  h,j,z=cb(r)
  c,e=be()
  m=len(c[1])
  for x in v(*c)if e else[]:s[int.from_bytes(x[:2])]=x[2:]
  if e:
   sz=int.from_bytes(e[:2])
   t=(sz+25)//26
   if sum(x in s for x in range(t))==t:
    g=b''.join(s[x]for x in range(t))[:sz]
    n=b(g)==int.from_bytes(e[2:])
  print('%d@ %d/%s'%(m,len(s),t))
 except:
  if not r:break
  print('cannot read')
if n:
 o=d(int.from_bytes(g),N2,open('b.py','rb').read())
 assert b(o)==B2
 open('c.py','wb').write(o)
# END READER
