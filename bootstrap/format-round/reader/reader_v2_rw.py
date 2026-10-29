# reader_v2_rw.py -- the format round's V2 'inverted' reader (2026-10-22,
# bootstrap/format-round/reader/make_readers.py from the ruled text below;
# the ring list, the ring check and n dropped; READERS.md = the diff).
# Then ruling 32's rename-and-rewrite search (format-
# round/reader/run_search_v.py, the changeset's rw/run_search.py under stage
# 1's a.py) respelled the region: names and equivalent spellings chosen by
# compressed size, the same program (the ruled text's functions, now: cb o,
# ft cb, a i; ld, v, be, rb, sp, dd, fr, f, ax, w, b keep their names).
# The ruled text's header follows.
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
# Only the region between the READER markers is typed, minus the shared
# block (the loader's d, here so the file runs on its own).  Run: python3
# reader_lite_v1.py beside b.py (the primer), one P5 PGM frame per line, an
# empty line or the end of input stops; a file that cannot be read is
# reported and skipped.
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
def o(c):
 s=open(c,'rb').read()
 m,n=[int(r)for r in s[:64].split()[1:3]]
 return m,n,s[len(s)-n*m:]
def b(c):
 s=2**32-1
 for i in c:
  s=i^s
  for x in range(8):s=3988292384*(s&1)^s>>1
 return s^2**32-1
y=[(x,y)for y in range(-8,8)for x in range(-8,8)]
def fr(s,x,y):
 return s[0]+(s[2][0]*x+s[3][0]*y)//17,s[1]+(s[2][1]*x+s[3][1]*y)//17
ou=[(x,y)for x,y in y if x*x+y*y>56][:68]
u=[(x,y,x+y&1)for y in range(-9,9)for x in range(-9,9)
 if{x,y}&{-9,8}]
def ax(x,y,p,r,t):
 s=4096-(r*r>>13)
 c=[17*p*s>>16,17*p*r>>16]
 b=[-17*p*r>>16,17*p*s>>16]
 for i in range(t):c,b=b,[-c[0],-c[1]]
 return[x,y,c,b]
def rb(s,x):
 s=min(max(s,0),16*h-17)
 x=min(max(x,0),16*j-17)
 q,y,i=s&15,x&15,h*(x>>4)+(s>>4)
 return((z[i]*(16-q)+z[i+1]*q)*(16-y)
  +(z[i+h]*(16-q)+z[i+h+1]*q)*y)//256
def dd(c):
 s=[]
 for i in range(j):
  for y,x in sp(c[h*i:h*i+h]):
   sz=y+2>>2
   if[s for s in s if s[2]*6>16*abs(s[0]-4*y)+16*abs(s[1]-16*i)]:
    continue
   q,n=max(0,i-x//2-2),min(j,i+x//2+3)
   m,r,t=min([(abs(r-4*(i-q)),r,t)for r,t in sp(c[h*q+sz:h*n:h])]
    +[(x,0,0)])
   if x<5*m:continue
   sz,p,z=4*y,32*(x+t)//5,4*(r+4*q)
   if min(sz,z)<p//2 or sz>16*h-p//2-32 or z>16*j-p//2-32:continue
   s+=[(sz,z,p)]
 return s
def sp(s):
 z,p,n=[0],s[0],0
 while n>=0:
  n=s.find(1-p,n)
  if n>0:p,z=1-p,z+[n]
 z+=[len(s)]
 return[(r+z[i+10]+z[i+11]-2,t)for i in range(1+s[0],len(z)-12,2)
  for r,t in[(z[i]+z[i+1],z[i+10]+z[i+11]-z[i]-z[i+1])]
  if t>23 and min(z[i]-z[i-1],z[i+12]-z[i+11])*40>=3*t and max(
  abs((z[i+h]+z[i+h+1]-r)*10-h*t)for h in(1,9,2,8,3,7)
  )<=(3*t+120)//10]
def cb(s,x):
 c=[(fr(s,x,y),1-2*(k^s[4]))for x,y,k in u]
 m=n=0
 for y in(x>>5,x>>6,x>>7,x//256):
  k,k,m,n=max((sum(rb(x+r,y+s)*t for(x,y),t in c),-abs(r-m)-abs(s-n)
   ,r,s)for r in(m-y,m,m+y)for s in(n-y,n,n+y))
 return m,n
def w(s):
 return sum(rb(*fr(s,x,y))*(1-2*k)for x,y,k in u)
def be(s):
 r,t=f(s)
 return i(r,t,y,32)if sum(r[x,y]<t for x,y in y)>3 else b''
def v(p,t):
 z={}
 f,i={},5*p>>4
 sz=[]
 for s in t:
  r=s[0]//i
  k=s[1]//i
  if(r,k)in z:continue
  z[r,k]=1
  if min(s[0],s[1],16*h-32-s[0],16*j-32-s[1])<5*p>>3:continue
  q,c,b=s[5]
  if c or b:
   m,n=cb(s,p)
   s[0],s[1]=s[0]+m,s[1]+n
   for x,y in((2,b),(3,c)):
    a=(y>0)-(y<0)
    g=f.get((q,c-a*(x>2),b-a*(x<3)))
    if g and a:s[x]=[a*(s[0]-g[0]),a*(s[1]-g[1])]
  r=(c or b)and be(s)
  if r:sz+=[r]
  if r!=None:
   f[q,c,b]=s
   t+=[[s[0]+y*s[2+x//2][0],s[1]+y*s[2+x//2][1],s[2],s[3],1-s[4],
    (q,c+y*(x>1),b+y*(x<2))]for x in range(4)for y in[1-2*(x&1)]]
 return sz
def f(s):
 sz={(x,y):rb(*fr(s,x,y))for y in range(-9,9)for x in range(-9,9)}
 z=sorted(sz[x,y]for x,y,k in u)
 return sz,z[8]+z[59]>>1
e,n,s,t=b'',0,{},'?'
def i(z,r,c,y):
 m=len(c)
 i=int(''.join('01'[r-z[i,k]+(z[i-1,k]+z[i+1,k]+z[i,k-1]+z[i,k+1]
  -4*z[i,k]>>1)>0]for i,k in c),2)
 for t in[0]+[1<<t for t in range(m*(y>20))]:
  s=i^t
  if s%2**y==b(e+(s>>y).to_bytes((m-y)//8,'big'))%2**y:
   return(s>>y).to_bytes((m-y)//8,'big')
def ld():
 c=dd(z.translate(bytes(x<t for t in[(min(z[::97])+max(z[::97]))//2]
  for x in range(256))))
 k,k,m,n=max((sum(abs(w(ax(x,y,p,r,t)))for x,y,p in c),-abs(r),r,t)
  for r in range(-640,641,64)for t in range(4))
 t=[]
 for x,y,p in c:
  s=ax(x,y,p,m,n)
  t+=[s+[int(w(s)<0),(len(t),0,0)]]
 b=e
 for s in t:b=b or i(*f(s),ou,20)
 return(c[0][2]if c else 0,t),b or e
while n<1:
 r=0
 try:
  r=input('file: ').strip()
  h,j,z=o(r)
  c,e=ld()
  m='%d bullseyes'%len(c[1])
  p=v(*c)if e else[]
 except:
  if not r:break
  m='cannot read'
  p=[]
 for x in p:s[int.from_bytes(x[:2],'big')]=x[2:]
 if e:
  sz=int.from_bytes(e[:2],'big')
  t=(sz+25)//26
  if t==sum(x in s for x in range(t)):
   g=b''.join(s[x]for x in range(t))[:sz]
   n=b(g)==int.from_bytes(e[2:],'big')
 print(r+':',m+',',len(p),'blocks accepted, chunks',len(s),'/',t,
  ['more','done'][n])
if n:
 a=d(int.from_bytes(g,'big'),N2,open('b.py','rb').read())
 assert b(a)==B2
 open('c.py','wb').write(a)
# END READER
