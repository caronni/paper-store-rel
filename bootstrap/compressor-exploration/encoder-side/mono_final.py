M=.0
C=None
A=len
B=range
A4=7016,4960
A5=3600/25.4
r=int((A4[0]-2*A5)//(64*3))
O=int((A4[1]-2*A5)//(64*3))
AM='holo/v2/1i%d-k-r0550-p100-v1@%dx%d'%(600//3,r,O)
P=r*O
AO=(1<<18)//P
s,Y=4096,2240
Z=s-Y
f=Y-32-100
t=f-1
Q=f+32,Y
R=s-100
AP,A6=50,.75
def A9(s,t):
	r=s<<32*t;A=int(r**(1/t))
	while A**t>r:A-=1
	while(A+1)**t<=r:A+=1
	return A&4294967295
AA=[A for A in B(2,312)if all(A%B for B in B(2,A))]
AR=[A9(A,2)for A in AA[:8]]
AS=[A9(A,3)for A in AA]
def u(r):
	K=r;L=4294967295
	def H(x,y):return(x>>y|x<<32-y)&L
	O=AR[:];y=A(K);K=bytes(K)+b'\x80'+bytes((55-y)%64)+(8*y).to_bytes(8,'big')
	for i in B(0,A(K),64):
		C=[int.from_bytes(K[i+4*A:i+4*A+4],'big')for A in B(16)]
		for G in B(16,64):R,S=C[G-15],C[G-2];C.append(C[G-16]+C[G-7]+(H(R,7)^H(R,18)^R>>3)+(H(S,17)^H(S,19)^S>>10)&L)
		E,M,N,T,F,P,Q,U=O
		for G in B(64):s=U+(H(F,6)^H(F,11)^H(F,25))+(F&P^~F&Q)+AS[G]+C[G];D=(H(E,2)^H(E,13)^H(E,22))+(E&M^E&N^M&N);U,Q,P,F,T,N,M,E=Q,P,F,T+s&L,N,M,E,s+D&L
		O=[A+B&L for(A,B)in zip(O,(E,M,N,T,F,P,Q,U))]
	return b''.join(A.to_bytes(4,'big')for A in O)
def g(A):return(A<<1^(283 if A&128 else 0))&255
def AT():
	A,C,N=[0]*255,[0]*256,1
	for U in B(255):A[U],C[N]=N,U;N^=g(N)
	F=[]
	for G in B(256):
		H=A[-C[G]%255]if G else 0;I=99
		for y in B(5):I^=(H<<y|H>>8-y)&255
		F.append(I)
	return F
N=AT()
L=[g(A)<<24|A<<16|A<<8|g(A)^A for A in N]
a=[(A>>8|A<<24)&4294967295 for A in L]
b=[(A>>16|A<<16)&4294967295 for A in L]
c=[(A>>24|A<<8)&4294967295 for A in L]
def AU(K):
	C=[int.from_bytes(K[A:A+4],'big')for A in B(0,16,4)];I=1
	for F in B(4,44):
		A=C[F-1]
		if F%4==0:A=(N[A>>16&255]<<24|N[A>>8&255]<<16|N[A&255]<<8|N[A>>24])^I<<24;I=g(I)
		C.append(C[F-4]^A)
	return C
def AV(s,r,t,p,y):
	E=y;D=p;C=t;A=r;A,C,D,E=A^s[0],C^s[1],D^s[2],E^s[3]
	for U in B(4,40,4):A,C,D,E=L[A>>24]^a[C>>16&255]^b[D>>8&255]^c[E&255]^s[U],L[C>>24]^a[D>>16&255]^b[E>>8&255]^c[A&255]^s[U+1],L[D>>24]^a[E>>16&255]^b[A>>8&255]^c[C&255]^s[U+2],L[E>>24]^a[A>>16&255]^b[C>>8&255]^c[D&255]^s[U+3]
	F=N;return[(F[B>>24]<<24|F[C>>16&255]<<16|F[D>>8&255]<<8|F[E&255])^s[40+A]for(A,(B,C,D,E))in enumerate(((A,C,D,E),(C,D,E,A),(D,E,A,C),(E,A,C,D)))]
def h(C,b,Y,r,X,D):A=r;O=AV(C,b<<24|Y<<16|A>>8,(A&255)<<24|X>>8,(X&255)<<24|D>>8,(D&255)<<24);return b''.join(A.to_bytes(4,'big')for A in O)
def AB(A):return AU(u(b'holo/v1|'+A.encode())[:16])
i=AB(AM)
AW=AB('holo/v1/sites/p100')
def AX(s,r,y):
	A,C,D,F,G,z=i,L,a,b,c,N;v=A[40]>>24;M=(1<<24|3<<16|s>>8)^A[0];O=A[3];p=[C[F&255^O>>24]^G[F>>8^A[2]&255]for F in B(y,y+64)];W=[]
	for X in B(r,r+64):
		P=((s&255)<<24|X>>8)^A[1];V=(X&255)<<24^A[2];Q=C[M>>24]^D[P>>16&255]^F[V>>8&255]^G[O&255]^A[4];R=C[P>>24]^D[V>>16&255]^F[O>>8&255]^G[M&255]^A[5];S=C[V>>24]^D[O>>16&255]^F[M>>8&255]^G[P&255]^A[6];x=D[M>>16&255]^F[P>>8&255]^A[7];o=C[Q>>24]^D[R>>16&255]^F[S>>8&255]^A[8];m=C[R>>24]^D[S>>16&255]^G[Q&255]^A[9];h=C[S>>24]^F[Q>>8&255]^G[R&255]^A[10];j=D[Q>>16&255]^F[R>>8&255]^G[S&255]^A[11]
		for t in p:
			I=x^t;E,H,J,K=o^G[I&255],m^F[I>>8&255],h^D[I>>16&255],j^C[I>>24]
			for U in B(12,36,4):E,H,J,K=C[E>>24]^D[H>>16&255]^F[J>>8&255]^G[K&255]^A[U],C[H>>24]^D[J>>16&255]^F[K>>8&255]^G[E&255]^A[U+1],C[J>>24]^D[K>>16&255]^F[E>>8&255]^G[H&255]^A[U+2],C[K>>24]^D[E>>16&255]^F[H>>8&255]^G[J&255]^A[U+3]
			l=C[E>>24]^D[H>>16&255]^F[J>>8&255]^G[K&255]^A[36];W.append((z[l>>24]^v)>>7)
	return W
def AY(C,b):
	while b:C,b=b,C%b
	return C
def AZ(u):
	r=65536-65536%R;C,E=[],0
	while A(C)<2:
		F=h(i,6,0,0,u,E)
		for U in B(0,16,2):
			D=F[U]<<8|F[U+1]
			if D<r and A(C)<2 and(C or AY(D%R,R)==1):C.append(D%R)
		E+=1
	return C
def AC(C,r):
	A=r;E=0
	while True:
		for D in h(AW,4,0,0,C,E):
			if D<256-256%A:return D%A
		E+=1
S=[A*64//10 for A in B(11)]
j=[(S[A//10]+AC(2*A,S[A//10+1]-S[A//10]),S[A%10]+AC(2*A+1,S[A%10+1]-S[A%10]))for A in B(100)]
Aa=set(A*64+B for(A,B)in j)
Ab=[A for A in B(64*64)if A not in Aa]
v=[h(i,2,3,0,A,0)[0]>>7 for A in B(100)]
def Ac():
	r,E=[],1
	for U in B(127):r.append(E);E=E<<1^(137 if E&64 else 0)
	I={B:A for(A,B)in enumerate(r)};H=set()
	for D in B(1,2*13+1):
		while D not in H:H.add(D);D=2*D%127
	C=[1]
	for D in H:C=[(C[F-1]if F else 0)^(r[(I[C[F]]+D)%127]if F<A(C)and C[F]else 0)for F in B(A(C)+1)]
	return sum(B<<A for(A,B)in enumerate(C))
Ad=Ac()
def w(s):
	E=sum((s>>17-A&1)<<A for A in B(18));A=E<<77
	for D in B(99,76,-1):
		if A>>D&1:A^=Ad<<D-77
	C=A|E<<77;return[C>>D&1^v[D]for D in B(100)]
Ae=int('2150898b671630317eaa5161f85f0174eeb56819a8155067dee11d5b0373f07699951294430cb08d2054e5a639bc880e7a3f4a197bfd1d6b2efe6b70020831185390bda4a5184aaf22f47016d2cad4ded00f97387b1335b05eefafe8931598703e8cb2a5c9d3bab317ee81b8f7d615f445340f3394f3b56bfa147f3e949911418e9c407a6a7e2c3ee098899dd85b4aba873551ae13d1a392938da3a152c4b3eec8ea496455f26723213ae4612554535a167140402a5267cc5ec5dce0d585fc9b84da68ebdd5fa7a0a401eb1d9dba4447cfecc9de3bd744029dcebbc0ca78b0426371ff928675b89413c35939773d8afd34fdcb85d1c573f04b5312f46ae7f5423e86fec13ddda43e4ade2f0b063e92d582d23ca74053b4b8264d1c7466d4769cd9dafbadd098caabfbe04a55fbffbdf7b87d1fa5fd1c13cdaaec16e73ac93263dbf0a7f3798786054afb04bc3c5927170113091ca9226d5eb1047132c4e38a423a115b0f28b086288439729e1c12c46f9034ff3fbd2b1c0560c712872e7207af1c3caa5a39ffc540a4fa7a2a388c5827f82706f3368d53d24bf803d9451d8bb857947965ff9d199d1793eb1d348c0f9126949a25661a1368310c73e65868ed7dea4f17ad2f71d3e5b274ee9df1a8098d55b7977468fe9c9aaec9a8f9bd20f8f4396c135866394eee34ac9c8e04440acce230e831200e5886abe3387894b1ec40e6f70f70c5cc4b452088eb02c0fcaa1c6950be802b20820c838fec71f0ac457ba1248cf9c28c5d2026cace9477fbedf1f8dc8b50a2b7a8bfcfe8bfc431bfbec50fe4418e9d9abe32c2e2b019403c5020dae9968bd5d5af92b6b35443f60f321a1138728d550f787469fdcc7dd14dc0984967b629852713ae95e57ebee2c16ed6467356619b82a9c88681092a5e304a9e43591123e721890be2352553da00e6faea7fe304c1d6a169d5d9a150be29046b12220757001c21f49ae3642a8a48f2e889f4a8eb4e7ae91ee65335166e187b43d3f10bad65329983e0c32fe448053db1670c137f873ea3aa0bacc36bf1db7ed5bb292e259960de798b368872df2183717b4c0ce5c3007e381c551898f50691781556c0ef9facd045dacb6d62eaed65e6bb7ffd3176b99cec9997ab71feaf80d2c79cc70b85de670ba7b1ff7d5ccaa0541efbc98c3577b28b3553a93bed1e64b90d2a2b297aaf5409b1e0dac7590e2f1eadcf1fbeae75102abdfce4b90f324ccebb9aacb8b67101651b7fef43e6d995c31fe6895f01859391f9904276735f55cb353aca972f080744c3546d2ee772e7610be000a199f7d6c7db497cc8dc558303381e26552dc3052b2b0a1ed4df29db4b4a5983a58f58a79003183c5b7d71341d0c9d7addff1dc94e5520a000b23a31a14ee777a0b2b8b53fdd95c3914cba7e42d74aa699018e324e5e5a74258b3821de5e2801a149fd18814b929924a492568902a8fe4fa7f7c6106f3c9cba1ebd8e3eb2a59bc07e13952f86d05f1717a73e8ed378b8eb08e432f33d405307c21334a5114b185a3840df80de3ce77f5b91c08865d3816b3bc0cfcfaf652c4f99f89f3d79e567f30ed1494fc7091d962977d980fae6bcd94072431d2633ccb2bbaed2dece0b68d4227667aefd9db05c64f2c084e80bb15736cb9585610c597a5564ae2f79d7ad2cc63f0eacb8ed0733d8d30fd78020cfe1a2a4377e5fb01332b1c4eb4c139d156cf1bcde2aad959e652f99297c1eea9cf9ed302e9dfb50dff26bee06a2c60b6ac46b2ad817afcc5a26cc43e2e3bb329ebb3cd24086a3111bdff2d578d3576808c9d4c15a456d13db13169ee19bf0a1c588ba19df23f7f8beb98d8fd17b6b6c1f3925b96445e3991a47abaf1e83eb39cd0f6bc353dd0e67ed3aa7d699696e8ca9d2909686081ec33d919c24e855e35d290b4fea229ee6cb4006384395ada359a3654fb00113d6de1f02b4dd445b44986a8ea5c7b07285ab4c11354e4f3ccc21a35159357b86997b8dd46d6c59f4f11ec93e561080c24d08f7fe859ed7d8ea3dfdcef96c104f1a4659a6a7d0ab8d15b492c26f23a4918d30debec2a54eeb002468c53755fb187a7d76614bb371cd586d18ccf045f2bd36b0b46d2f931b56e169a72f5993df5328fd4573f0dbe5a3d314ef0155aaba0808d5f43e08e2f2468100060a12c84daa79092de294fc835ed78f7b95921ce8ef62176b152fd7cc9eeebf5523c58afc44cf3c26b3b668e18ae3d57ad8331991369762e337faaad27e09f38a6bc1fde4fb7f8a1ed65effd23155fc0ba3aecf7efc5ee5ef096a772c57ae220b9900ad987fbfe87437b7091fa0937f252e65da47338f315d9d3fde5924d61a2083a80cee17103d17586e5a028fbe382c485a8bd07b0608a8803a4c4c8365fa86963bc0891e3179169022e5cc50f4d1d7cba1ddb7a9640e9ee2bdbfe45464dcdec98160a4e98f6c3b8e9e13745cf58bceccc8e282add2b226e9ac19baa50f434c4db5fac1839d82f660c92680d743990885b5fe2eacd97802840a1d0112c1b01afbfbe796132c7afa6ad4246932794c4148714015a2be7e719571c214c6e014ad703a78ce14ece3d42f5a69f9bb89da396191f53b2169845628ec0f19f3d451c87b0dc2c45a0ac5f7f7c57fcc360fb23e83e1193818199459dfbfcd44be0f017a834776dac8180964ba954bb6d8b3a2f54ea9e01112a2583dad46f6d1c4407884de5f979ff34ef1e4ab14457a8bc249c720a09b958f1a54347b68b8f0175a16571671be8769fb0e2842353290298ef7035812eebdbd47a5fae2027ff620d89aa3b3ae3abc4b0b470493927c0370682571737fcddfd3b0a4facdc26aad3b63236d2a6f1936aa40458f5a59b7f8784188be5a77c0faddd64748c28d75e1d72a2a7564d42d2c593040f09041441f0b74a5a3baa52340652edcc2aa89054d2051576daba3be39cac12fddfa46ab09b0123df60d9810b542ba189910a85abcf61eaaba9818fc5361edbdc6ad860f3ab297db897619e0d4783b63cf060a3b4714769864b249037ce65c041d570ad7eb7021e2f32395ead5e4b1c17fa836dcecb77584335a2d74e87807257dd6239e3dc62629830b207b0e3d6448c9789c98ba284241556e8dfb88fbec760a3794a4e9fc16cb71efd592764714af435298c32686a7c8cca08017af4298a8178406c00f59618437fec5241716397e6344d62f5493bd8a64eac8dd80fcbb11fae1568a3211298d69da11000b6f43c1552d0d9fe9ef63eb6ae37fc1ba7ed6b1f042eee5e327996409d4817f00371a03a00b54e92f9980453dbc61acae26d527aaa9fab86980f683854df3c84dc4a6de3c86f6f99107f40cba952280d7597477092b46b38a72d33947a91f052e6d828678e096a03cfb7c6793a2b37b821cf0889ab00afef2a8ddd8249d2006eb',16)
def Af():
	C=Ae
	def H(D):nonlocal C;C,L=divmod(C,D);return L
	I=list(B(Z));J=[I.pop(H(Z-A))for A in B(Z)];E=[[]for A in B(Z)]
	for(D,F)in enumerate([10]*10+[3]*25):
		L=[H(29)for A in B(F)];M=[H(64)for A in B(F)]
		for(N,O)in zip(L,M):
			for G in B(64):E[J[N*64+G]].append(D*64+(G+O)%64)
	for A in B(Z):E[A]+=[Y+A]+([Y+A-1]if A else[])
	return[[A for A in A if not Q[0]<=A<Q[1]]for A in E]
x=Af()
def AD(L):return all(sum(L[A]<0 for A in B)%2==0 for B in x)
def Ag(L):
	L=L[:]
	if AD(L):return L
	O=[[M]*A(B)for B in x]
	for X in B(AP):
		for(r,J)in zip(x,O):
			K=[L[A]-B for(A,B)in zip(r,J)];D=E=1e30;H=I=0
			for(F,C)in enumerate(K):
				if C<0:I^=1;C=-C
				if C<D:D,E,H=C,D,F
				elif C<E:E=C
			D,E=D*A6,E*A6
			for(F,U)in enumerate(r):
				C=K[F];G=E if F==H else D
				if I^(C<0):G=-G
				J[F]=G;L[U]=C+G
		if AD(L):return L
AE=[]
for k in B(256):
	for _ in B(8):k=k>>1^(3988292384 if k&1 else 0)
	AE.append(k)
def AF(r):
	A=4294967295
	for B in r:A=AE[(A^B)&255]^A>>8
	return A^4294967295
def Ah(L):
	C=''.join('1'if L[A]<0 else'0'for A in B(Q[0]));A,E=int(C[:f],2),int(C[f:],2)
	if AF((A<<4).to_bytes(264,'big'))!=E:return
	return A>>t,A&(1<<t)-1
AG=[((1,0),(0,1)),((0,1),(-1,0)),((-1,0),(0,-1)),((0,-1),(1,0))]
AH=[(0,0),(0,63),(63,63),(63,0)]
class Ai:
	def __init__(B,c,r):
		G=b' \t\r\n';E=open(c,'rb').read();F,C=[],2
		if E[:2]!=b'P5':raise ValueError('not a binary PGM (P5)')
		while A(F)<3:
			while E[C]in G:C+=1
			if E[C]==35:
				while E[C]not in b'\r\n':C+=1
				continue
			D=C
			while E[C]not in G:C+=1
			F.append(int(E[D:C]))
		B.W,B.H,I=F;B.Q=2 if I>255 else 1;B.P,B.R,B.O=E,C+1,B.W*B.Q;B.c=3*r/600;B.S=max(2,round(.7*B.c));B.j=max(1,B.S//4)
	def N(A,i,n):
		D=A.S;F,E=int(i-D/2+.5),int(n-D/2+.5)
		if F<0 or E<0 or F+D>A.H or E+D>A.W:return
		K,Q,U=A.P,A.j,A.Q;r=A.R+F*A.O+E*U;return sum(sum(K[A:A+D*U:Q*U])for A in B(r,r+D*A.O,Q*A.O))
	def at(A,lat,b,c):B,C,D,E,F,I=lat;return A.N(B+b*D+c*F,C+b*E+c*I)
	def b(W,lat,ci,cj,f,t):
		K=[[M]*8 for A in B(8)]
		for D in B(8):
			for F in B(8):
				I=[W.at(lat,ci+A+D/8-.5,cj+C+F/8-.5)for A in B(-f,f+1,t)for C in B(-f,f+1,t)];I=[A for A in I if A is not C]
				if A(I)<20:return
				E=sum(I)/A(I);K[D][F]=sum((A-E)**2 for A in I)/A(I)
		s=max((K[D][F],D,F)for D in B(8)for F in B(8));U,D,F=s
		def h(i,F,D):A=i-2*F+D;return M if A>=0 else max(-.5,min(.5,.5*(i-D)/A))/8
		P=D/8-.5+h(K[D-1][F],K[D][F],K[(D+1)%8][F]);Q=F/8-.5+h(K[D][F-1],K[D][F],K[D][(F+1)%8]);x=min(min(A)for A in K);return s[0],P,Q,s[0]/max(x,1e-09)
	def w(s):
		K=s.c
		for(f,g)in((.5,.5),(.35,.5),(.65,.5),(.5,.3),(.5,.7),(.3,.3),(.7,.7),(.3,.7),(.7,.3)):
			e,i=s.H*f,s.W*g;D=C
			for T in B(-20,21):
				Q,U=Aj(T*.5);W=e,i,K*Q,-K*U,K*U,K*Q;E=s.b(W,0,0,24,3)
				if E and(D is C or E[0]>D[0][0]):D=E,W
			if not D or D[0][3]<2.:continue
			(n,y,p,n),(L,M,F,G,H,I)=D;J=[(0,0,L+y*F+p*H,M+y*G+p*I)];W=J[0][2],J[0][3],F,G,H,I;N,O=8,0
			while N<4000 and O<2:
				l=A(J)
				for(x,r)in((0,1),(0,-1),(1,0),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)):
					for t in(0,.25,-.25,.5,-.5):
						R,S=round(N*(x-r*t)),round(N*(r+x*t));E=s.b(W,R,S,8,1)
						if E and E[3]>2. and abs(E[1])<.35 and abs(E[2])<.35:L,M,F,G,H,I=W;b,c=R+E[1],S+E[2];J.append((R,S,L+b*F+c*H,M+b*G+c*I));break
				O=O+1 if A(J)==l else 0;W=AI(J,W);N*=2
			L,M,F,G,H,I=W;J=[A for A in J if(L+A[0]*F+A[1]*H-A[2])**2+(M+A[0]*G+A[1]*I-A[3])**2<(.3*K)**2];L,M,F,G,H,I=W=AI(J,W);a,V=(F*F+G*G)**.5,(H*H+I*I)**.5
			if A(J)>=12 and abs(a/K-1)<.06 and abs(V/K-1)<.06 and abs(F*H+G*I)<.035*a*V:return W
	def u(s,lat,ci,cj):
		F=192;x=[[s.at(lat,ci+G,cj+A)for A in B(F)]for G in B(F)];I=sorted(A for I in x for A in I if A is not C)
		if A(I)<F*F//2:return
		V=(I[A(I)//10]+I[A(I)*9//10])/2;K=[[2 if A is C else int(A<V)for A in B]for B in x];D=C
		for E in B(4):
			(W,Q),(H,R)=AG[E];a,S=AH[E];L=[(a+W*A+Q*B,S+H*A+R*B)for(A,B)in j];y=[(L[A],v[A])for A in B(95,100)]
			for G in B(F-64):
				for M in B(F-64):
					if any(K[G+A][M+B]!=C for((A,B),C)in y):continue
					J=0
					for T in B(77,95):O,U=L[T];J=J<<1|(K[G+O][M+U]^v[T])&1
					if J//P>=AO:continue
					c=w(J);N=sum(K[G+A][M+B]!=C for((A,B),C)in zip(L,c))
					if N<=13 and(D is C or N<D[0]):D=N,E,ci+G,cj+M,J
		return D
	def a(A,lat,s,E):a,f,B,C,D,F=lat;(G,H),(I,J)=AG[A.U];Q,R=AH[A.U];S,U=64*(s[0]-A.z[0]),64*(s[1]-A.z[1]);W=A.E[0]+G*S+H*U+Q+E[0];c=A.E[1]+I*S+J*U+R+E[1];return a+W*B+c*D,f+W*C+c*F,G*B+I*D,G*C+I*F,H*B+J*D,H*C+J*F
	def g(A,lat,tile,d):D,M,F,G,H,I=A.a(lat,tile,d);return[A.N(D+c*F+p*H,M+c*G+p*I)for(c,p)in j]
	def V(s,lat,tile,d,word):
		F=0
		for(A,B)in zip(s.g(lat,tile,d),word):
			if A is C:return
			F+=-A if B else A
		return F
	def f(s,lat,tile,d,word):
		P=tile;W=lat;J=word
		for(f,g)in((2,.25),(5,.5)):
			D=C
			for T in B(-f,f+1):
				for U in B(-f,f+1):
					F=d[0]+T*g,d[1]+U*g;I=s.V(W,P,F,J)
					if I is not C and(D is C or I>D[0]):D=I,F
			if D is C:return
			for G in(g/2,g/4):
				E=D[1]
				for F in((E[0]-G,E[1]),(E[0]+G,E[1]),(E[0],E[1]-G),(E[0],E[1]+G)):
					I=s.V(W,P,F,J)
					if I is not C and I>D[0]:D=I,F
			F=D[1];O=s.g(W,P,F);K=[A for(A,B)in zip(O,J)if B];M=[A for(A,B)in zip(O,J)if not B];V=(sum(K)/A(K)+sum(M)/A(M))/2
			if sum((A<V)!=B for(A,B)in zip(O,J))<=20:return F
	def e(s,lat,tile,d,word):D,R,S,Q,U,V=s.a(lat,tile,d);N=s.N;L=[N(D+G*S+J*U,R+G*Q+J*V)for G in B(64)for J in B(64)];I=[(L[A*64+B],C)for((A,B),C)in zip(j,word)];K=[A for(A,B)in I if B];J=[A for(A,B)in I if not B];G,F=sum(K)/A(K),sum(J)/A(J);x=(sum((A-G)**2 for A in K)+sum((A-F)**2 for A in J))/A(I);a,E=(F-G)/max(x,1e-09),(F+G)/2;return[M if A is C else max(-2e1,min(2e1,(A-E)*a))for A in L]
def Aj(K):
	F=K*3.141592653589793/180;D=E=M;J=1.
	for A in B(30):
		if A%4==0:D+=J
		elif A%4==1:E+=J
		elif A%4==2:D-=J
		else:E-=J
		J*=F/(A+1)
	return D,E
def AI(J,W):
	G=[[M]*3 for A in B(3)];H,I=[M]*3,[M]*3
	for(f,c,N,O)in J:
		D=1.,f,c
		for A in B(3):
			for F in B(3):G[A][F]+=D[A]*D[F]
			H[A]+=D[A]*N;I[A]+=D[A]*O
	E,s=AJ(G,H),AJ(G,I)
	if E is C or s is C:return W
	return E[0],s[0],E[1],s[1],E[2],s[2]
def AJ(A,n):
	def g(A):return A[0][0]*(A[1][1]*A[2][2]-A[1][2]*A[2][1])-A[0][1]*(A[1][0]*A[2][2]-A[1][2]*A[2][0])+A[0][2]*(A[1][0]*A[2][1]-A[1][1]*A[2][0])
	F=g(A)
	if abs(F)<1e-06*(A[1][1]*A[2][2]+1):return
	return[g([[n[C]if F==H else A[C][F]for F in B(3)]for C in B(3)])/F for H in B(3)]
l=[1]
def AK(E):
	while A(l)<=E:k=l[-1];l.append(k<<1&16777215^(27 if k&8388608 else 0))
	return l[E]
def y(M,E):return bin(M&AK(E)).count('1')&1
def AL(s):return sum((s>>1+A&1)<<17-A for A in B(18))
def Ak(B):
	I={}
	for(r,C)in B.items():
		M=AK(r)
		while M:
			D=(M&-M).bit_length()-1
			if D not in I:I[D]=M,C;break
			M^=I[D][0];C^=I[D][1]
		if not M and C:raise ValueError('metadata bits contradict each other')
	if A(I)<24 or A(B)<48:return
	E=0
	for D in sorted(I,reverse=True):M,C=I[D];E|=(C^bin(M&E).count('1')%2)<<D
	F=AL(E)
	if E&1 or E>>19 or not F:raise ValueError('metadata: unsupported version or reserved bits set')
	if F>16384:raise ValueError('K = %d: a multi-block volume (> 4.3 MB), not handled here'%F)
	return E
class T(Exception):0
class Al:
	def __init__(B,s,d):B.M,B.K,B.J=s,AL(s),d;B.s={};B.G={};B.F=[];B.I=C;B.D=C
	def T(B,D):B.L=dict(B.s),dict(B.G),B.I;B.F.append(D)
	def m(B):B.s,B.G,B.I=B.L;B.F.pop()
	def d(D,M):A=(D.K+127)//128;E=int.from_bytes(b''.join(h(i,7,0,0,M,F)for F in B(A)),'big');return int(bin(E|1<<128*A)[3:][::-1],2)&(1<<D.K)-1
	def add(B,t,y):
		E=y;D=t;I=B.s.get(D)
		if I is not C:
			if I!=E:raise T('tile %d differs from the one read before'%D)
			return
		B.s[D]=E
		if B.I is not C:return
		M=1<<D if D<B.K else B.d(D);F=E
		while M:
			U=(M&-M).bit_length()-1;H=B.G.get(U)
			if H is C:
				B.G[U]=M,F
				if A(B.G)==B.K:B.k()
				return
			M^=H[0];F^=H[1]
		if F:raise T('tile %d contradicts the tiles read before'%D)
	def k(B):
		D,G=B.K,t;H=[0]*D
		for U in sorted(B.G,reverse=True):
			Q,F=B.G[U];I=Q>>U+1
			while I:s=I&-I;F^=H[U+s.bit_length()];I^=s
			H[U]=F
		E=0
		for y in H:E=E<<G|y
		M=-D*G%8;C=(E<<M).to_bytes((D*G+M)//8,'big');J=int.from_bytes(C[32:36],'big');K=8*(36+J)
		if 36+J>A(C)or-(-K//G)!=D or E&(1<<D*G-K)-1 or u(C[36:36+J])!=C[:32]:raise T('the volume solves, but its SHA-256 is wrong')
		B.I=C[36:36+J]
	def x(B):return'volume %d: symbols held %d / needed %d; %s'%(B.J,A(B.s),B.K,'done'if B.I is not C else'more')
class Am:
	def __init__(B):B.C=[];B.B=[]
	def A(B,E):
		I={A:B for(A,B,C)in E};J=[A for A in B.C if all(y(A.M,B)==C for(B,C)in I.items())]
		if A(I)>=24 and A(J)==1:return J[0]
		H=Ak(I)
		if H is C:return
		for D in B.C:
			if D.M==H:return D
		B.C.append(Al(H,A(B.C)+1));return B.C[-1]
	def r(B,C,E,F,D):
		A=E
		if y(C.M,A)!=F:raise T("tile %d carries another volume's metadata"%A)
		C.add(A,D)
	def y(B,E,r,t):
		A=r;A.T(E)
		try:
			for U in t:B.r(A,*U)
		except T as C:A.m();return B.n(E,A,C)
		return''
	def n(D,E,B,M):return'%s REFUSED (%s): it has the size of volume %d but not its content, so it or one of the scans %s is from another volume of that size; its tiles are not used'%(E,M,B.J,', '.join(B.F))
	def l(D,y,dpi):
		E=y;G=Ai(E,dpi);H=G.w()
		if H is C:return'%s: no cell lattice found (dpi %d right? one page, whole?)'%(E,dpi)
		I=D.h(G,H)
		if I is C:return'%s: no tile address found (wrong FORMAT_ID, a mirror-image scan, or not this row?)'%E
		M,F,B,Z=D.i,[],C,'';Q=0
		for(J,U)in I.items():
			K=M*P+J[0]*O+J[1]
			if B is not C:
				if B.I is not C:break
				if K in B.s:continue
			Q+=1;r=D.v(G,H,J,U,K)
			if not r:continue
			F.append((K,)+r)
			if B is C:
				B=D.A(F)
				if B is not C:B.T(E);L=F
				else:L=[]
			else:L=F[-1:]
			try:
				for t in L:D.r(B,*t)
			except T as R:B.m();Z='; '+D.n(E,B,R);break
		S='%s: page %d, turn %d, tiles placed %d/%d, decoded %d, certified %d; '%(E,M,90*G.U,A(I),P,Q,A(F))
		if B is C:
			if F:D.B.append((E,F))
			return S+'too few to tell its volume, set aside'+D.p()
		return S+B.x()+Z+D.p()
	def p(B):
		D=''
		try:B.A([A for(B,D)in B.B for A in D])
		except ValueError:0
		for F in B.B[:]:
			E,I=F;J=[A for A in B.C if all(y(A.M,B)==C for(B,C,D)in I)]
			if A(J)==1 and A(I)>=8:B.B.remove(F);D+='; '+(B.y(E,J[0],I)or'%s, set aside before, now in %s'%(E,J[0].x()))
		return D
	def h(F,s,d):
		G=d;B=s
		for(L,M)in((-96,-96),(-300,-96),(108,-96),(-96,-300),(-96,108),(-500,-96),(308,-96),(-96,-500),(-96,308)):
			I=B.u(G,L,M)
			if not I:continue
			S,B.U,y,Q,R=I;B.E=y,Q;F.i,i=divmod(R,P);B.z=divmod(i,O);E,J,H,K={},[],[B.z],{B.z}
			while H:
				C=H.pop(0)
				if not F.t(B,G,C,E):J.append(C)
				for(N,U)in((0,1),(1,0),(0,-1),(-1,0)):
					D=C[0]+N,C[1]+U
					if 0<=D[0]<r and 0<=D[1]<O and D not in K:K.add(D);H.append(D)
			for C in J:F.t(B,G,C,E)
			if A(E)>=3:return E
	def t(F,s,lat,t,y):
		S=y;D=t;E=[]
		for f in(1,2,3,4):
			E=[S[D[0]+T,D[1]+U]for T in B(-f,f+1)for U in B(-f,f+1)if(D[0]+T,D[1]+U)in S]
			if E:break
		d=(sum(A[0]for A in E)/A(E),sum(A[1]for A in E)/A(E))if E else(0,0);J=F.i*P+D[0]*O+D[1];I=s.f(lat,D,d,w(J))
		if I is not C:S[D]=I
		return I is not C
	def v(G,t,lat,tile,i,y):
		E=y;D=tile;J=w(E);I=t.e(lat,D,i,J);L=AX(G.i,64*D[0],64*D[1]);N,O=AZ(E);A=[M]*s
		for C in B(R):F=Ab[(N*C+O)%R];H=I[F];A[C if C<Q[0]else C+Q[1]-Q[0]]=-H if L[F]else H
		A=Ag(A);return A and Ah(A)
def An(d):
	y,AG=int.from_bytes(d[4:12],'big'),d[16:]+bytes(8);E,D,i=2**32-1,1460000,28;w=E*E+E+E;b,f,AH=[0]*4096,[0]*1024,0x7fffffe87fffffe03ff000000000000
	for F in B(4096):b[F]=D>>20;D+=D*((4096<<20)-D)>>40;f[b[F]>>2]=F-2048
	P,o,g,AI=1<<i,68-i,2654435761,0x9e3779b97f4a7c15;n=memoryview(bytearray(b'\x80'*(2*P+263168))).cast('H');AJ=memoryview(bytearray(b'\x80'*30)).cast('H');A4=memoryview(bytearray(P)).cast('I');I=memoryview(bytearray(44605440)).cast('i');p,m,e=[32768]*32,[0]*32,[0]*9;z=[655360//(A*10+12)for A in B(31)];R=[b[min(4095,A%33*128)]*16 for A in B(2162688)];W=R[:];c=bytearray(8+y);J=L=F=h=M=G=A6=Q=C=0;a=V=8
	for U in B(8,y+8):
		H,K=c[U-1],1;M=(M<<8|H)&w>>8
		if AH>>H&1:G=(G+H+1)*773&E
		elif G:A6,G=G,0
		if H==10:a,V=V,U
		AK=c[min(a+U-V,V-1)]<<8|min(U-V,40);AL=[0,0,M&65535,M&16777215,M&E,G,AK,M,G+A6*31337+1];C,Q=(C+(C<15))*(C>0),Q+1;v=M*g>>50-i&(P>>2)-1;Q=Q if C else A4[v];C,A4[v]=C or int(Q>0),U
		for j in B(8):
			if j==0 or j==4:
				e[0],e[1]=P+K*16,P+512+H*512+K*16
				for D in B(2,9):
					d=((AL[D]*16+D)*32+K)*AI&w;A,t=d>>o<<4,d>>o-16&65535
					if n[A]!=t:
						if n[A^16]==t:A^=16
						else:
							if n[A+1]&15>n[A^17]&15:A^=16
							n[A],n[A+1:A+16]=t,AJ
					e[D]=A
				T=1
			u=[A+T for A in e];AA=c[Q]>>7-j&1;S=C*2+AA;AB=[f[n[A]>>6]for A in u]+[f[p[S]>>6]];AC,AD=(K+256*min(C,3))*10,(1024+H*256+K)*10;AE=(66560+((M&65535)*g>>20&4095)*256+K)*10;AM=sum([(I[AC+D]+I[AD+D]+I[AE+D]*2+65536)*AB[D]for D in B(10)])>>18;Z=max(-2047,min(2047,AM))+2048;AF,O=b[Z],Z&127;Y=(H*256+K)*33+(Z>>7);X=((M&16777215)*g>>16&65535)*33+(Z>>7);r=2*AF+3*(R[Y]*(128-O)+R[Y+1]*O>>11);r=max(1,min(4095,r+3*(W[X]*(128-O)+W[X+1]*O>>11)>>3))
			while(J^L)>>24==0:J,L=J<<8&E,L<<8&E|255;F,h=F<<8&E|AG[h],h+1
			l=J+(L-J>>12)*r;J,L,N=(J,l,1)if F<=l else(l+1,L,0);Y,X=Y+(O>>6),X+(O>>6);R[Y]+=(N<<16)-R[Y]>>6;W[X]+=(N<<16)-W[X]>>6
			for A in u:k,x=n[A]>>4,n[A]&15;k+=((N<<12)-k)*z[x]>>16;n[A]=k<<4|x+(x<15)
			p[S]+=((N<<16)-p[S])*z[m[S]]>>16;m[S]+=m[S]<30;AN=(N<<12)-AF
			for D in B(10):s=AB[D]*AN>>11;I[AC+D]+=s;I[AD+D]+=s;I[AE+D]+=s
			K,T=K+K+N,T+T+N;C=C*(AA==N)
		c[U]=K&255
	return bytes(c[8:])
def Ao(K):
	A=0
	while K[A]:D,A=K[A:A+512],A+512;C=(D[345:500]+b'/'+D[:100]).replace(b'\x00',b'').lstrip(b'/').decode();J=int(D[124:135],8);print(C);open(C.replace('%','%25').replace('/','%2F'),'wb').write(K[A:A+J]);A+=J+511&-512
def Ap():
	D=Am()
	while True:
		try:E=input('scan (PGM file [dpi]; empty line ends): ').split()
		except EOFError:break
		if not E:break
		try:print(D.l(E[0],int(E[1])if A(E)>1 else 1200))
		except(OSError,ValueError,IndexError)as R:print('%s: %s'%(E[0],R))
		for B in D.C:
			if B.I is not C and B.D is C:
				F=sum(B.D is not C for B in D.C);B.D='payload.bin' if not F else 'payload.bin'.replace('.','-%d.'%(F+1));open(B.D,'wb').write(B.I);print('volume %d complete: %d bytes, SHA-256 %s, written to %s'%(B.J,A(B.I),u(B.I).hex(),B.D))
				if B.I[:4]==b'R3A1':
					print('archive: decoding');J=An(B.I)
					if AF(J)==int.from_bytes(B.I[12:16],'big'):Ao(J)
					else:print('archive: CRC-32 wrong')
	for B in D.C:
		if B.I is C:print('volume %d not complete (scans %s): %s'%(B.J,', '.join(B.F),B.x()))
	for(r,I)in D.B:print('%s: its %d tiles never found their volume'%(r,A(I)))
	if not D.C:print('no volume found')
if __name__=='__main__':Ap()
