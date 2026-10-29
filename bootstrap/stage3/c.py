K=.0
E=sum
C=None
A=len
B=range
A4=7016,4960
A5=3600/25.4
t=int((A4[0]-2*A5)//(64*3))
Q=int((A4[1]-2*A5)//(64*3))
AM='holo/v2/1i%d-k-r0547-p100-v1@%dx%d'%(600//3,t,Q)
R=t*Q
AO=(1<<18)//R
u,Z=4096,2240
a=u-Z
f=Z-32-100
v=f-1
S=f+32,Z
T=u-100
AP,A6=50,.8
def A9(s,r):
	g=s<<32*r;A=int(g**(1/r))
	while A**r>g:A-=1
	while(A+1)**r<=g:A+=1
	return A&4294967295
AA=[A for A in B(2,312)if all(A%s for s in B(2,A))]
AR=[A9(A,2)for A in AA[:8]]
AS=[A9(A,3)for A in AA]
def w(t):
	g=t;L=4294967295
	def H(A,r):return(A>>r|A<<32-r)&L
	O=AR[:];r=A(g);g=bytes(g)+b'\x80'+bytes((55-r)%64)+(8*r).to_bytes(8,'big')
	for s in B(0,A(g),64):
		C=[int.from_bytes(g[s+4*A:s+4*A+4],'big')for A in B(16)]
		for G in B(16,64):R,S=C[G-15],C[G-2];C.append(C[G-16]+C[G-7]+(H(R,7)^H(R,18)^R>>3)+(H(S,17)^H(S,19)^S>>10)&L)
		E,M,N,T,F,P,Q,U=O
		for G in B(64):D=U+(H(F,6)^H(F,11)^H(F,25))+(F&P^~F&Q)+AS[G]+C[G];Z=(H(E,2)^H(E,13)^H(E,22))+(E&M^E&N^M&N);U,Q,P,F,T,N,M,E=Q,P,F,T+D&L,N,M,E,D+Z&L
		O=[A+B&L for(A,B)in zip(O,(E,M,N,T,F,P,Q,U))]
	return b''.join(A.to_bytes(4,'big')for A in O)
def g(A):return(A<<1^(283 if A&128 else 0))&255
def AT():
	C,M,A=[0]*255,[0]*256,1
	for U in B(255):C[U],M[A]=A,U;A^=g(A)
	F=[]
	for G in B(256):
		O=C[-M[G]%255]if G else 0;L=99
		for r in B(5):L^=(O<<r|O>>8-r)&255
		F.append(L)
	return F
N=AT()
M=[g(A)<<24|A<<16|A<<8|g(A)^A for A in N]
b=[(A>>8|A<<24)&4294967295 for A in M]
c=[(A>>16|A<<16)&4294967295 for A in M]
d=[(A>>24|A<<8)&4294967295 for A in M]
def AU(M):
	C=[int.from_bytes(M[A:A+4],'big')for A in B(0,16,4)];L=1
	for F in B(4,44):
		A=C[F-1]
		if F%4==0:A=(N[A>>16&255]<<24|N[A>>8&255]<<16|N[A&255]<<8|N[A>>24])^L<<24;L=g(L)
		C.append(C[F-4]^A)
	return C
def AV(s,r,t,p,g):
	E=g;D=p;C=t;A=r;A,C,D,E=A^s[0],C^s[1],D^s[2],E^s[3]
	for U in B(4,40,4):A,C,D,E=M[A>>24]^b[C>>16&255]^c[D>>8&255]^d[E&255]^s[U],M[C>>24]^b[D>>16&255]^c[E>>8&255]^d[A&255]^s[U+1],M[D>>24]^b[E>>16&255]^c[A>>8&255]^d[C&255]^s[U+2],M[E>>24]^b[A>>16&255]^c[C>>8&255]^d[D&255]^s[U+3]
	F=N;return[(F[T>>24]<<24|F[C>>16&255]<<16|F[D>>8&255]<<8|F[U&255])^s[40+A]for(A,(T,C,D,U))in enumerate(((A,C,D,E),(C,D,E,A),(D,E,A,C),(E,A,C,D)))]
def h(C,M,N,T,X,D):A=T;O=AV(C,M<<24|N<<16|A>>8,(A&255)<<24|X>>8,(X&255)<<24|D>>8,(D&255)<<24);return b''.join(A.to_bytes(4,'big')for A in O)
def AB(A):return AU(w(b'holo/v1|'+A.encode())[:16])
i=AB(AM)
AW=AB('holo/v1/sites/p100')
def AX(s,r,t):
	A,C,D,F,G,z=i,M,b,c,d,N;y=A[40]>>24;L=(1<<24|3<<16|s>>8)^A[0];O=A[3];a=[C[U&255^O>>24]^G[U>>8^A[2]&255]for U in B(t,t+64)];W=[]
	for X in B(r,r+64):
		P=((s&255)<<24|X>>8)^A[1];V=(X&255)<<24^A[2];Q=C[L>>24]^D[P>>16&255]^F[V>>8&255]^G[O&255]^A[4];R=C[P>>24]^D[V>>16&255]^F[O>>8&255]^G[L&255]^A[5];S=C[V>>24]^D[O>>16&255]^F[L>>8&255]^G[P&255]^A[6];x=D[L>>16&255]^F[P>>8&255]^A[7];o=C[Q>>24]^D[R>>16&255]^F[S>>8&255]^A[8];g=C[R>>24]^D[S>>16&255]^G[Q&255]^A[9];h=C[S>>24]^F[Q>>8&255]^G[R&255]^A[10];j=D[Q>>16&255]^F[R>>8&255]^G[S&255]^A[11]
		for k in a:
			T=x^k;E,H,I,K=o^G[T&255],g^F[T>>8&255],h^D[T>>16&255],j^C[T>>24]
			for U in B(12,36,4):E,H,I,K=C[E>>24]^D[H>>16&255]^F[I>>8&255]^G[K&255]^A[U],C[H>>24]^D[I>>16&255]^F[K>>8&255]^G[E&255]^A[U+1],C[I>>24]^D[K>>16&255]^F[E>>8&255]^G[H&255]^A[U+2],C[K>>24]^D[E>>16&255]^F[H>>8&255]^G[I&255]^A[U+3]
			n=C[E>>24]^D[H>>16&255]^F[I>>8&255]^G[K&255]^A[36];W.append((z[n>>24]^y)>>7)
	return W
def AY(C,n):
	while n:C,n=n,C%n
	return C
def AZ(t):
	g=65536-65536%T;C,r=[],0
	while A(C)<2:
		F=h(i,6,0,0,t,r)
		for U in B(0,16,2):
			D=F[U]<<8|F[U+1]
			if D<g and A(C)<2 and(C or AY(D%T,T)==1):C.append(D%T)
		r+=1
	return C
def AC(t,p):
	T=p;r=0
	while True:
		for D in h(AW,4,0,0,t,r):
			if D<256-256%T:return D%T
		r+=1
U=[A*64//10 for A in B(11)]
j=[(U[A//10]+AC(2*A,U[A//10+1]-U[A//10]),U[A%10]+AC(2*A+1,U[A%10+1]-U[A%10]))for A in B(100)]
Aa=set(A*64+B for(A,B)in j)
Ab=[A for A in B(64*64)if A not in Aa]
x=[h(i,2,3,0,A,0)[0]>>7 for A in B(100)]
def Ac():
	c,F=[],1
	for G in B(127):c.append(F);F=F<<1^(137 if F&64 else 0)
	z={B:A for(A,B)in enumerate(c)};a=set()
	for D in B(1,2*13+1):
		while D not in a:a.add(D);D=2*D%127
	C=[1]
	for D in a:C=[(C[F-1]if F else 0)^(c[(z[C[F]]+D)%127]if F<A(C)and C[F]else 0)for F in B(A(C)+1)]
	return E(B<<A for(A,B)in enumerate(C))
Ad=Ac()
def y(s):
	C=E((s>>17-A&1)<<A for A in B(18));A=C<<77
	for D in B(99,76,-1):
		if A>>D&1:A^=Ad<<D-77
	F=A|C<<77;return[F>>A&1^x[A]for A in B(100)]
Ae=int('1566e0df6832b9583f676d4bd9b01ccb8a8d9c338e2699b961c1db7cfeb4558160fbf1e1f46f3f2989acec7f415cfb8155f5325f7edc9b79eb6c670773b239cd81f5a05bac8ade9696ca9a3862843f3f743dc3f471305156d33757c5b79edc576959d1494f69e350fb6ac57ceb2c2f165c34043e1415442be74d4b94bd97d5436ee2ffa918df9eed6999763224cecc48f6e39a248fe6c28b4f8b04de449a0cc80c429250b1d948315b9ad0af434e9541e2c42e2f203170e197a54ee0a2bd0a54114fc9e6e629f97298f0adbd84489fc3b07b127df24c77985a918758a153c01e47b2c8041c6d49c3cce6b3c8d237709f9bd5b327bee0d1234ff3fe9a46e78a6b26243833461df09f5a21690f3f39ba4f4df9e46b84701c4754b5948146b850d20421669b8aeab82b616fd5ae71f3e6fc8f7fe0083401f447db9a3ecdfffc52da50945eacb1a0c5a26bb53c4ec6484e43e62498f1d865d02e6a41e1fd0ea40810f1cb92c716cd86af73f9df10cb452bf8fbc543a57cd940edb3cc0f459e346cfc5a1a0736d94b9e5bb464cd1efbd519c7ceeac5f93f5770eaa6224c74dbc7b84e795d14335f82e7f5209acbe3f3395e489b1c6e23412e525d4c6e5a210f9938be54b0e117af4777bb8c1f8c3d0d6bfbf67d816eee368abf133c24f58e9454222aeb96d105885714acf0298119d1db0401e502bb1ca7ef6341f4d413b0aa52d461f9ba6b85ac252f160588f26df25433e71145b110451e44effb32b4d52db4127e39a0f1f33db4dcbe5a94a6714055bd46f323b2895618dc07c32503c61020679bdb6a83424328e15c602c133e0bb3a63ed1820ef02ef33621e033177943eacb6404d9ff6d0230ff12c3ff849acb54066b11179a47a2b176ced279582669cf5745023c49e3bbdcf2bf828cb4813d8f002abfb3ff4d606f077226dbb61b3eb81d933a5572e686497cbbea7315dd7f620bf7e24a303b33a3756ad7ea5b1bea28f31f461d14e4ac1951b1e03573129a588a0cdceee95a7e1648ed44b0a7666dde115408614138648901b3572428b8f3cd17f4078fef4b2d76bf6c1a178ebfa52965f6da6fc6355c794a2d80bcdab0adb0b258c5689e50abe34e9e4003467f27cfd1ca8881fe8b49d12f7a48c72f512678f676e720371f3a464968a1e2c2e08b4589a4d463ea0981923789af601e21b15fed13c92f98e4181356d4520b3361c40b8734f41d3b4a8ed8aa30cd496eb5b3cda549df2e29d2c6e8896948ef271e543ea2f59d5e9a431358240c0c60beb37b37cd5d1d89f465cd588e6ac36a3ea090fa92b51db65cb5362fb0387dcaad7271867b6a8ec168e112460e685755ccd1821d1922e67ceb51a247b5812d0ba6ab212080310151751215a12f6f75de2b1bdbb618643bfeaa2ab84079d8e41271fba76ac3fc7f02c44dd70fe2d78e7bb254a79c19b452cf8ea5ed38f098e6f8dda651f66e2392ea652f462e101804323b2f2b5c057bfb2773ddf14d105b513f749cd8fd854cab894c851a9e566c035d3e7719077088b6b87f9e552b5371ae87b38ca72e6538974546feb9a481911770a72bcc686e04152100fa09dfdf36f117a72c581cb62e933f3cd4ffc4ae8b5bc9b94b9e48eaf9b7a846fdcfa94e8e6515c26ee589240703acbae9bf9a906262d2ccde81db870ad70eda2e0c43ef86d42ef8d33b4dd7ac92958092286fa907a4454dd2f7be023519876b48ff290088f6a6ed34fc4bfdf10c8a0e3f8e96a4c2e5db82dbf3877dc6cc7b905f0fe88f5ca08a0c002d11ee90db2a4002a30c214763fb4406107badcfe618622e9442c5ed3995b415eaab557569c342655c5235231ed82b5a417e29d89191be21a5a9b0b90f0ee3b9e20bf584c1e2f8b79a96f07b57ecff2a3d28d29c8a6b56d52f1864995e8f8f06b165c2064c461182bc7b1e2e3b0abab619cb700bfdec27491e70ad4843d6db22d85317cdc1ad49e086f39d5686e9764cec9362edd87b51cabbdcd488efdbe11df469d25b8d02711c0e9bcb6f3a168433d45aecdf4ed59af5b5f33901c403027b48fd716ec6b1aaeca8f2b37cdd5328ac526a1b4cabe19cdc2272ec3aee701e69c5122ed91f83aaae8ca5f34f72449e6ecdf8d2b887a1e5f2e42a251cec85d392ca07eb5cd5a113c70debce5995efecd4752ab386f2ae8bd51f68479237bbb870e54954745b8ac9524c22b5ddb6c7f509af992d61574e8e3f9ab379d49eecc37b8008455b9321a0f893d7e1179d46d8a8ead4a4c8736db2868ed5d411bc5f42bdbc1b72b8f6f5b2bb8624f2696989a4137e6520691064ee69fbb6da8f5e1265edc0ae55348c06d7ff749b33e4526988b1eef336b014e7867dfc1096aa8249529ad920c517ab8aa3329e5e18a00d092347cf172539d8e82dd48f19335a61eb91075d23cc14f997373f7b2a37e669493e5b4dde31492fc0eacf84684af550fc2b3a87a4119aeab5d2b751eb336d013a5318d0bf2f9973a2b8e3d6bbaa6311244dc6949a0ad736735169b6f40f881997e998962f90d8516a858e1d563c5debf2637236ac039732e04838d714cb5ee32a088543436c81ddcbc6db6f7493624dbe0460552208b6ee8a3a6e600fe26fe6184f113fa13e664b3d6f08af1b4fe9a25a61033563a1ba31a1d8ebebfce39ecd2b7982f867a053d425b87445ad1980928fbf95b82d654dba42bd92aa1966eac0e4197fbeda7932a3f95df2e55dc94c56445ea34764089d0964e70f619ab85936e54a416a39714abc8e63580a7b5ec1ad1a1434a492199686658b6a5d30951b76ab0e804b661c834a888ed6a9a103e91fad444695c4aba5894e34ddb60c4af67fff920603af0e40abebd695bfadcf5daa21120e47406ea3f2b88d37e4e1db64dd728cd391e557feeadf3cde2d959483e898f94e17311d6dcf0459dd2ef83e055b9f29b0707dad42b418f1eeaa12a4896f8f336a9a3ce4a059dd5d5076d7bfcd2b331d5fd10e4184869085418925036d47381c4a793b39cab8b3983d4bf0203fbb0f100f7cb9640f0fc52f2bddb7ccebc0521237d5a39898ff2d13cdf0779d61003f6cef6fba2bb483cc95f4a27f44e77361a790ef6c9f02684ed52490f5dc0acfe3a43822933127ad0da525932141c2c908b429d24e3567c3bdae5e9e94fb6ad06d5ba7fd5ddfe990d92da0915cf6cb16be086caf74de6db2404f1d538507c37fc54de3488d7332497b16a102708a6e265faa21cc2181dba9f2bd6c5f0c2fbfdd16bdde73bd5c847107b8acee8dd97522d4f2814892c56e9628e4545424412b9fec4cceb3fcac7c91cfb67a350ad868d77ab477fa6d320a9e8d57bcf820d861aa10bdb1b388d9439534471bc8539e7ce85dc529681696b9c5fc2cc08331769ef084f22ce7b8701be0c20668a9a6f15c1e1354576c5db1413b0da07eb39a65',16)
def Af():
	C=Ae
	def f(n):nonlocal C;C,F=divmod(C,n);return F
	H=list(B(a));G=[H.pop(f(a-A))for A in B(a)];D=[[]for A in B(a)]
	for(E,F)in enumerate([10]*10+[3]*25):
		L=[f(29)for A in B(F)];M=[f(64)for A in B(F)]
		for(T,P)in zip(L,M):
			for U in B(64):D[G[T*64+U]].append(E*64+(U+P)%64)
	for A in B(a):D[A]+=[Z+A]+([Z+A-1]if A else[])
	return[[A for A in A if not S[0]<=A<S[1]]for A in D]
z=Af()
def AD(L):return all(E(L[A]<0 for A in B)%2==0 for B in z)
def Ag(L):
	L=L[:]
	if AD(L):return L
	r=[[K]*A(B)for B in z]
	for k in B(AP):
		for(H,J)in zip(z,r):
			M=[L[A]-B for(A,B)in zip(H,J)];D=E=1e30;G=P=0
			for(F,C)in enumerate(M):
				if C<0:P^=1;C=-C
				if C<D:D,E,G=C,D,F
				elif C<E:E=C
			D,E=D*A6,E*A6
			for(F,U)in enumerate(H):
				C=M[F];O=E if F==G else D
				if P^(C<0):O=-O
				J[F]=O;L[U]=C+O
		if AD(L):return L
AE=[]
for k in B(256):
	for _ in B(8):k=k>>1^(3988292384 if k&1 else 0)
	AE.append(k)
def AF(a):
	A=4294967295
	for D in a:A=AE[(A^D)&255]^A>>8
	return A^4294967295
def Ah(L):
	C=''.join('1'if L[A]<0 else'0'for A in B(S[0]));A,E=int(C[:f],2),int(C[f:],2)
	if AF((A<<4).to_bytes(264,'big'))!=E:return
	return A>>v,A&(1<<v)-1
AG=[((1,0),(0,1)),((0,1),(-1,0)),((-1,0),(0,-1)),((0,-1),(1,0))]
AH=[(0,0),(0,63),(63,63),(63,0)]
class Ai:
	def __init__(B,c,r):
		a=b' \t\r\n';E=open(c,'rb').read();F,C=[],2
		if E[:2]!=b'P5':raise ValueError('not a binary PGM (P5)')
		while A(F)<3:
			while E[C]in a:C+=1
			if E[C]==35:
				while E[C]not in b'\r\n':C+=1
				continue
			O=C
			while E[C]not in a:C+=1
			F.append(int(E[O:C]))
		B.W,B.H,H=F;B.S=2 if H>255 else 1;B.Q,B.G,B.Z=E,C+1,B.W*B.S;B.O=3*r/600;B.n(B.O)
	def n(A,r):A.ap=max(2,round(.7*r));A.R=max(1,A.ap//4)
	def z(A,n,t):
		D=A.ap;F,C=int(n-D/2+.5),int(t-D/2+.5)
		if F<0 or C<0 or F+D>A.H or C+D>A.W:return
		L,I,H=A.Q,A.R,A.S;r=A.G+F*A.Z+C*H;return E(E(L[A:A+D*H:I*H])for A in B(r,r+D*A.Z,I*A.Z))
	def X(s,lat,i,c):A,C,D,E,F,G=lat;return s.z(A+i*D+c*F,C+i*E+c*G)
	def j(N,lat,ci,cj,k,p):
		L=[[K]*8 for A in B(8)]
		for D in B(8):
			for F in B(8):
				H=[N.X(lat,ci+A+D/8-.5,cj+G+F/8-.5)for A in B(-k,k+1,p)for G in B(-k,k+1,p)];H=[A for A in H if A is not C]
				if A(H)<20:return
				O=E(H)/A(H);L[D][F]=E((A-O)**2 for A in H)/A(H)
		s=max((L[A][F],A,F)for A in B(8)for F in B(8));S,D,F=s
		def h(i,k,p):A=i-2*k+p;return K if A>=0 else max(-.5,min(.5,.5*(i-p)/A))/8
		P=D/8-.5+h(L[D-1][F],L[D][F],L[(D+1)%8][F]);G=F/8-.5+h(L[D][F-1],L[D][F],L[D][(F+1)%8]);R=min(min(A)for A in L);return s[0],P,G,s[0]/max(R,1e-09)
	def h(A):
		for(D,C)in((.5,.5),(.35,.5),(.65,.5),(.5,.3),(.5,.7),(.3,.3),(.7,.7),(.3,.7),(.7,.3)):
			F,G=A.H*D,A.W*C
			for r in(1,.96,1.04):
				L=A.O*r;A.n(L);O=A.c(F,G,L)
				if O:yield O
	def c(y,q,j,p):
		K=C
		for s in B(-20,21):
			V,r=Aj(s*.5);D=q,j,p*V,-p*r,p*r,p*V;E=y.j(D,0,0,8,1)
			if E and(K is C or E[0]>K[0][0]):K=E,D
		if K and K[0][3]>1.2:
			(W,X,Y,W),(L,P,F,G,H,I)=K;J=[(0,0,L+X*F+Y*H,P+X*G+Y*I)];D=J[0][2],J[0][3],F,G,H,I;N,O=4,0
			while N<4000 and O<2:
				g=A(J)
				for(i,k)in((0,1),(0,-1),(1,0),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)):
					for t in(0,.25,-.25,.5,-.5):
						R,S=round(N*(i-k*t)),round(N*(k+i*t));E=y.j(D,R,S,8,1)
						if E and E[3]>1.2 and abs(E[1])<.35 and abs(E[2])<.35:L,P,F,G,H,I=D;c,Z=R+E[1],S+E[2];J.append((R,S,L+c*F+Z*H,P+c*G+Z*I));break
				O=O+1 if A(J)==g else 0;D=AI(J,D);N*=2
			L,P,F,G,H,I=D;J=[A for A in J if(L+A[0]*F+A[1]*H-A[2])**2+(P+A[0]*G+A[1]*I-A[3])**2<(.3*p)**2];L,P,F,G,H,I=D=AI(J,D);T,U=(F*F+G*G)**.5,(H*H+I*I)**.5
			if A(J)>=12 and abs(T/p-1)<.06 and abs(U/p-1)<.06 and abs(F*H+G*I)<.035*T*U:y.n((T+U)/2);return D
	def e(N,lat,ci,cj):
		F=192;M=[[N.X(lat,ci+L,cj+G)for G in B(F)]for L in B(F)];H=sorted(A for J in M for A in J if A is not C)
		if A(H)<F*F//2:return
		V=(H[A(H)//10]+H[A(H)*9//10])/2;I=[[2 if A is C else int(A<V)for A in A]for A in M];D=C
		for t in B(4):
			(W,X),(i,Z)=AG[t];U,r=AH[t];P=[(U+W*A+X*B,r+i*A+Z*B)for(A,B)in j];z=[(P[A],x[A])for A in B(95,100)]
			for L in B(F-64):
				for G in B(F-64):
					if any(I[L+A][G+B]!=C for((A,B),C)in z):continue
					J=0
					for T in B(77,95):c,S=P[T];J=J<<1|(I[L+c][G+S]^x[T])&1
					if J//R>=AO:continue
					g=y(J);O=E(I[L+A][G+B]!=C for((A,B),C)in zip(P,g))
					if O<=13 and(D is C or O<D[0]):D=O,t,ci+L,cj+G,J
		return D
	def k(A,t,s,I):L,P,B,C,D,E=t;(G,H),(i,Z)=AG[A.m];T,S=AH[A.m];F,U=64*(s[0]-A.Y[0]),64*(s[1]-A.Y[1]);X=A.I[0]+G*F+H*U+T+I[0];W=A.I[1]+i*F+Z*U+S+I[1];return L+X*B+W*D,P+X*C+W*E,G*B+i*D,G*C+i*E,H*B+Z*D,H*C+Z*E
	def f(O,lat,tile,d):A,P,F,G,H,I=O.k(lat,tile,d);return[O.z(A+i*F+Z*H,P+i*G+Z*I)for(i,Z)in j]
	def x(O,lat,tile,d,word):
		F=0
		for(A,B)in zip(O.f(lat,tile,d),word):
			if A is C:return
			F+=-A if B else A
		return F
	def y(N,lat,tile,d,t):
		P=tile;O=lat;J=t
		for(k,L)in((2,.25),(5,.5)):
			D=C
			for T in B(-k,k+1):
				for U in B(-k,k+1):
					F=d[0]+T*L,d[1]+U*L;H=N.x(O,P,F,J)
					if H is not C and(D is C or H>D[0]):D=H,F
			if D is C:return
			for G in(L/2,L/4):
				I=D[1]
				for F in((I[0]-G,I[1]),(I[0]+G,I[1]),(I[0],I[1]-G),(I[0],I[1]+G)):
					H=N.x(O,P,F,J)
					if H is not C and H>D[0]:D=H,F
			F=D[1];Q=N.f(O,P,F);M=[A for(A,B)in zip(Q,J)if B];W=[A for(A,B)in zip(Q,J)if not B];V=(E(M)/A(M)+E(W)/A(W))/2
			if E((A<V)!=B for(A,B)in zip(Q,J))<=20:return F
	def v(O,lat,tile,d,p):D,R,F,T,N,V=O.k(lat,tile,d);g=O.z;P=[g(D+A*F+G*N,R+A*T+G*V)for A in B(64)for G in B(64)];J=[(P[A*64+B],C)for((A,B),C)in zip(j,p)];L=[A for(A,B)in J if B];H=[A for(A,B)in J if not B];M,I=E(L)/A(L),E(H)/A(H);x=(E((A-M)**2 for A in L)+E((A-I)**2 for A in H))/A(J);U,r=(I-M)/max(x,1e-09),(I+M)/2;return[K if A is C else max(-2e1,min(2e1,(A-r)*U))for A in P]
def Aj(s):
	F=s*3.141592653589793/180;D=E=K;I=1.
	for A in B(30):
		if A%4==0:D+=I
		elif A%4==1:E+=I
		elif A%4==2:D-=I
		else:E-=I
		I*=F/(A+1)
	return D,E
def AI(J,F):
	D=[[K]*3 for A in B(3)];H,I=[K]*3,[K]*3
	for(L,M,N,U)in J:
		P=1.,L,M
		for A in B(3):
			for G in B(3):D[A][G]+=P[A]*P[G]
			H[A]+=P[A]*N;I[A]+=P[A]*U
	E,s=AJ(D,H),AJ(D,I)
	if E is C or s is C:return F
	return E[0],s[0],E[1],s[1],E[2],s[2]
def AJ(A,n):
	def g(A):return A[0][0]*(A[1][1]*A[2][2]-A[1][2]*A[2][1])-A[0][1]*(A[1][0]*A[2][2]-A[1][2]*A[2][0])+A[0][2]*(A[1][0]*A[2][1]-A[1][1]*A[2][0])
	F=g(A)
	if abs(F)<1e-06*(A[1][1]*A[2][2]+1):return
	return[g([[n[C]if F==G else A[C][F]for F in B(3)]for C in B(3)])/F for G in B(3)]
l=[1]
def AK(g):
	while A(l)<=g:F=l[-1];l.append(F<<1&16777215^(27 if F&8388608 else 0))
	return l[g]
def A0(M,H):return bin(M&AK(H)).count('1')&1
def AL(s):return E((s>>1+A&1)<<17-A for A in B(18))
def Ak(J):
	L={}
	for(H,I)in J.items():
		M=AK(H)
		while M:
			D=(M&-M).bit_length()-1
			if D not in L:L[D]=M,I;break
			M^=L[D][0];I^=L[D][1]
		if not M and I:raise ValueError('metadata bits contradict each other')
	if A(L)<24 or A(J)<48:return
	E=0
	for D in sorted(L,reverse=True):M,I=L[D];E|=(I^bin(M&E).count('1')%2)<<D
	C=AL(E)
	if E&1 or E>>19 or not C:raise ValueError('metadata: unsupported version or reserved bits set')
	if C>16384:raise ValueError('K = %d: a multi-block volume (> 4.3 MB), not handled here'%C)
	return E
class V(Exception):0
class Al:
	def __init__(A,B,r):A.M,A.K,A.J=B,AL(B),r;A.L={};A.P={};A.F=[];A.s=C;A.r=C
	def B(A,r):A.N=dict(A.L),dict(A.P),A.s;A.F.append(r)
	def a(A):A.L,A.P,A.s=A.N;A.F.pop()
	def g(A,r):C=(A.K+127)//128;E=int.from_bytes(b''.join(h(i,7,0,0,r,t)for t in B(C)),'big');return int(bin(E|1<<128*C)[3:][::-1],2)&(1<<A.K)-1
	def add(B,t,g):
		E=g;D=t;H=B.L.get(D)
		if H is not C:
			if H!=E:raise V('tile %d differs from the one read before'%D)
			return
		B.L[D]=E
		if B.s is not C:return
		M=1<<D if D<B.K else B.g(D);O=E
		while M:
			F=(M&-M).bit_length()-1;L=B.P.get(F)
			if L is C:
				B.P[F]=M,O
				if A(B.P)==B.K:B.T()
				return
			M^=L[0];O^=L[1]
		if O:raise V('tile %d contradicts the tiles read before'%D)
	def T(B):
		D,S=B.K,v;L=[0]*D
		for G in sorted(B.P,reverse=True):
			Q,M=B.P[G];I=Q>>G+1
			while I:F=I&-I;M^=L[G+F.bit_length()];I^=F
			L[G]=M
		J=0
		for U in L:J=J<<S|U
		E=-D*S%8;C=(J<<E).to_bytes((D*S+E)//8,'big');H=int.from_bytes(C[32:36],'big');r=8*(36+H)
		if 36+H>A(C)or-(-r//S)!=D or J&(1<<D*S-r)-1 or w(C[36:36+H])!=C[:32]:raise V('the volume solves, but its SHA-256 is wrong')
		B.s=C[36:36+H]
	def E(B):return'volume %d: symbols held %d / needed %d; %s'%(B.J,A(B.L),B.K,'done'if B.s is not C else'more')
class Am:
	def __init__(A):A.C=[];A.D=[]
	def A(B,r):
		D={A:B for(A,B,C)in r};J=[A for A in B.C if all(A0(A.M,B)==C for(B,C)in D.items())]
		if A(D)>=24 and A(J)==1:return J[0]
		E=Ak(D)
		if E is C:return
		for F in B.C:
			if F.M==E:return F
		B.C.append(Al(E,A(B.C)+1));return B.C[-1]
	def U(B,C,M,E,r):
		A=M
		if A0(C.M,A)!=E:raise V("tile %d carries another volume's metadata"%A)
		C.add(A,r)
	def V(B,G,r,t):
		A=r;A.B(G)
		try:
			for C in t:B.U(A,*C)
		except V as f:A.a();return B.l(G,A,f)
		return''
	def l(G,B,d,t):return'%s REFUSED (%s): it has the size of volume %d but not its content, so it or one of the scans %s is from another volume of that size; its tiles are not used'%(B,t,d.J,', '.join(d.F))
	def t(O,t,p):
		J=p;G=t;D=Ai(G,J);g=F=C;I=[J]+[C for(B,C)in sorted((abs(A-J),A)for A in(600,1200,2400)if A!=J)]
		for(i,k)in enumerate(I):
			if i:print('%s: no tile placed at %d dpi, trying %d dpi'%(G,I[i-1],k))
			D.O=3*k/600
			for E in D.h():
				g=E;F=O.b(D,E)
				if F:break
			if F:break
		if g is C:return'%s: no cell lattice found at %s dpi (one page, whole?)'%(G,', '.join(map(str,I)))
		if F is C:return'%s: no tile address found (wrong FORMAT_ID, a mirror-image scan, or not this row?)'%G
		print('%s: cell lattice found, %d tiles placed, decoding'%(G,A(F)));S,H,B,r=O.i,[],C,'';P=0
		for(L,U)in F.items():
			M=S*R+L[0]*Q+L[1]
			if B is not C:
				if B.s is not C:break
				if M in B.L:continue
			P+=1;W=O.w(D,E,L,U,M)
			if not W:continue
			H.append((M,)+W)
			if B is C:
				B=O.A(H)
				if B is not C:B.B(G);N=H
				else:N=[]
			else:N=H[-1:]
			try:
				for T in N:O.U(B,*T)
			except V as f:B.a();r='; '+O.l(G,B,f);break
		K='%s: page %d, turn %d, tiles placed %d/%d, decoded %d, certified %d; '%(G,S,90*D.m,A(F),R,P,A(H))
		if B is C:
			if H:O.D.append((G,H))
			return K+'too few to tell its volume, set aside'+O.p()
		return K+B.E()+r+O.p()
	def p(B):
		E=''
		try:B.A([A for(J,D)in B.D for A in D])
		except ValueError:0
		for F in B.D[:]:
			G,C=F;D=[A for A in B.C if all(A0(A.M,B)==C for(B,C,D)in C)]
			if A(D)==1 and A(C)>=8:B.D.remove(F);E+='; '+(B.V(G,D[0],C)or'%s, set aside before, now in %s'%(G,D[0].E()))
		return E
	def b(c,u,p):
		G=p;B=u
		for(L,M)in((-96,-96),(-300,-96),(108,-96),(-96,-300),(-96,108),(-500,-96),(308,-96),(-96,-500),(-96,308)):
			F=B.e(G,L,M)
			if not F:continue
			V,B.m,N,O,P=F;B.I=N,O;c.i,S=divmod(P,R);B.Y=divmod(S,Q);E,J,H,a={},[],[B.Y],{B.Y}
			while H:
				C=H.pop(0)
				if not c.d(B,G,C,E):J.append(C)
				for(T,U)in((0,1),(1,0),(0,-1),(-1,0)):
					D=C[0]+T,C[1]+U
					if 0<=D[0]<t and 0<=D[1]<Q and D not in a:a.add(D);H.append(D)
			for C in J:c.d(B,G,C,E)
			if A(E)>=3:return E
	def d(O,sc,lat,t,p):
		P=p;D=t;F=[]
		for k in(1,2,3,4):
			F=[P[D[0]+G,D[1]+A]for G in B(-k,k+1)for A in B(-k,k+1)if(D[0]+G,D[1]+A)in P]
			if F:break
		V=(E(A[0]for A in F)/A(F),E(A[1]for A in F)/A(F))if F else(0,0);g=O.i*R+D[0]*Q+D[1];H=sc.y(lat,D,V,y(g))
		if H is not C:P[D]=H
		return H is not C
	def w(c,p,lat,t,s,g):
		F=g;D=t;E=y(F);L=AX(c.i,64*D[0],64*D[1]);U,P=AZ(F)
		for G in((0,0),(.125,0),(-.125,0),(0,.125),(0,-.125)):
			J=p.v(lat,D,(s[0]+G[0],s[1]+G[1]),E);A=[K]*u
			for C in B(T):X=Ab[(U*C+P)%T];H=J[X];A[C if C<S[0]else C+S[1]-S[0]]=-H if L[X]else H
			A=Ag(A);W=A and Ah(A)
			if W:return W
def An(e):
	a,AH=int.from_bytes(e[4:12],'big'),e[16:]+bytes(8);H,C,p=2**32-1,1460000,28;y=H*H+H+H;Y,f,AI=[0]*4096,[0]*1024,0x7fffffe87fffffe03ff000000000000
	for F in B(4096):Y[F]=C>>20;C+=C*((4096<<20)-C)>>40;f[Y[F]>>2]=F-2048
	c,u,m,AJ=1<<p,68-p,2654435761,0x9e3779b97f4a7c15;n=memoryview(bytearray(b'\x80'*(2*c+263168))).cast('H');AK=memoryview(bytearray(b'\x80'*30)).cast('H');z=memoryview(bytearray(c)).cast('I');L=memoryview(bytearray(44605440)).cast('i');r,s,d=[32768]*32,[0]*32,[0]*9;w=[655360//(A*10+12)for A in B(31)];P=[Y[min(4095,A%33*128)]*16 for A in B(2162688)];T=P[:];b=bytearray(8+a);R=S=F=i=N=K=q=M=J=0;A8=Z=8
	for G in B(8,a+8):
		D,I=b[G-1],1;N=(N<<8|D)&y>>8
		if AI>>D&1:K=(K+D+1)*773&H
		elif K:q,K=K,0
		if D==10:A8,Z=Z,G
		AL=b[min(A8+G-Z,Z-1)]<<8|min(G-Z,40);AM=[0,0,N&65535,N&16777215,N&H,K,AL,N,K+q*31337+1];J,M=(J+(J<15))*(J>0),M+1;v=N*m>>50-p&(c>>2)-1;M=M if J else z[v];J,z[v]=J or int(M>0),G
		for k in B(8):
			if k==0 or k==4:
				d[0],d[1]=c+I*16,c+512+D*512+I*16
				for C in B(2,9):
					e=((AM[C]*16+C)*32+I)*AJ&y;A,g=e>>u<<4,e>>u-16&65535
					if n[A]!=g:
						if n[A^16]==g:A^=16
						else:
							if n[A+1]&15>n[A^17]&15:A^=16
							n[A],n[A+1:A+16]=g,AK
					d[C]=A
				V=1
			AA=[A+V for A in d];AB=b[M]>>7-k&1;X=J*2+AB;AC=[f[n[A]>>6]for A in AA]+[f[r[X]>>6]];AD,AE=(I+256*min(J,3))*10,(1024+D*256+I)*10;AF=(66560+((N&65535)*m>>20&4095)*256+I)*10;AN=E([(L[AD+C]+L[AE+C]+L[AF+C]*2+65536)*AC[C]for C in B(10)])>>18;h=max(-2047,min(2047,AN))+2048;AG,Q=Y[h],h&127;U=(D*256+I)*33+(h>>7);W=((N&16777215)*m>>16&65535)*33+(h>>7);j=2*AG+3*(P[U]*(128-Q)+P[U+1]*Q>>11);j=max(1,min(4095,j+3*(T[W]*(128-Q)+T[W+1]*Q>>11)>>3))
			while(R^S)>>24==0:R,S=R<<8&H,S<<8&H|255;F,i=F<<8&H|AH[i],i+1
			l=R+(S-R>>12)*j;R,S,O=(R,l,1)if F<=l else(l+1,S,0);U,W=U+(Q>>6),W+(Q>>6);P[U]+=(O<<16)-P[U]>>6;T[W]+=(O<<16)-T[W]>>6
			for A in AA:o,x=n[A]>>4,n[A]&15;o+=((O<<12)-o)*w[x]>>16;n[A]=o<<4|x+(x<15)
			r[X]+=((O<<16)-r[X])*w[s[X]]>>16;s[X]+=s[X]<30;AO=(O<<12)-AG
			for C in B(10):t=AC[C]*AO>>11;L[AD+C]+=t;L[AE+C]+=t;L[AF+C]+=t
			I,V=I+I+O,V+V+O;J=J*(AB==O)
		b[G]=I&255
		if(G-7)*20//a>(G-8)*20//a:print('archive: %d%% decoded'%((G-7)*20//a*5))
	return bytes(b[8:])
def Ao(L):
	A=0
	while L[A]:D,A=L[A:A+512],A+512;F=(D[345:500]+b'/'+D[:100]).replace(b'\x00',b'').lstrip(b'/').decode();C=int(D[124:135],8);print(F);open(F.replace('%','%25').replace('/','%2F'),'wb').write(L[A:A+C]);A+=C+511&-512
def Ap():
	F=Am()
	while True:
		try:D=input('scan (PGM file [dpi]; empty line ends): ').split()
		except EOFError:break
		if not D:break
		try:print(F.t(D[0],int(D[1])if A(D)>1 else 1200))
		except(OSError,ValueError,IndexError)as f:print('%s: %s'%(D[0],f))
		for B in F.C:
			if B.s is not C and B.r is C:
				O=E(B.r is not C for B in F.C);B.r='payload.bin' if not O else 'payload.bin'.replace('.','-%d.'%(O+1));open(B.r,'wb').write(B.s);print('volume %d complete: %d bytes, SHA-256 %s, written to %s'%(B.J,A(B.s),w(B.s).hex(),B.r))
				if B.s[:4]==b'R3A1':
					print('archive: decoding');g=An(B.s)
					if AF(g)==int.from_bytes(B.s[12:16],'big'):Ao(g)
					else:print('archive: CRC-32 wrong')
	for B in F.C:
		if B.s is C:print('volume %d not complete (scans %s): %s'%(B.J,', '.join(B.F),B.E()))
	for(L,M)in F.D:print('%s: its %d tiles never found their volume'%(L,A(M)))
	if not F.C:print('no volume found')
if __name__=='__main__':Ap()
