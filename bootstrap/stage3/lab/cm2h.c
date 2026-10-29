/* cm2h: handle-based mirror of a.py's d() model (ideal bits), exact integer counts.
   Key (h&(256**o-1),u) = value of the last o bytes (leading zero bytes stripped) + u.
   Generation-stamped table (no clearing between evaluations); checkpoint + undo log
   for evaluating many continuations of one prefix. */
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>
typedef struct { uint8_t k[16]; uint8_t len; uint8_t pad; uint16_t u; uint32_t gen; uint32_t c[2]; } E; /* 32 B */
typedef struct { uint32_t idx; uint32_t c0, c1; uint32_t fresh; } U;
typedef struct { E*T; size_t M; uint32_t gen; int O[32]; int no;
  uint8_t *hist; long nh, caph;
  U*ul; size_t nul, capul; int logging; } H;
static uint64_t hsh(const uint8_t*k,int len,int u){uint64_t h=1469598103934665603ULL^(uint64_t)u*0x9E3779B97F4A7C15ULL^len;for(int i=0;i<len;i++){h^=k[i];h*=1099511628211ULL;}h^=h>>29;h*=0xbf58476d1ce4e5b9ULL;h^=h>>32;return h;}
H* cm2_new(long maxbytes,const int*O,int no){H*h=calloc(1,sizeof(H));h->M=1024;while(h->M<(size_t)maxbytes*8*no)h->M<<=1;h->T=calloc(h->M,sizeof(E));h->gen=1;h->no=no;memcpy(h->O,O,no*sizeof(int));h->caph=maxbytes+64;h->hist=malloc(h->caph);h->capul=1<<20;h->ul=malloc(h->capul*sizeof(U));return h;}
void cm2_free(H*h){free(h->T);free(h->hist);free(h->ul);free(h);}
static void ulog(H*h,uint32_t idx,uint32_t*c,int fresh){if(!h->logging)return;if(h->nul==h->capul){h->capul*=2;h->ul=realloc(h->ul,h->capul*sizeof(U));}U*x=&h->ul[h->nul++];x->idx=idx;x->c0=c[0];x->c1=c[1];x->fresh=fresh;}
static uint32_t* look(H*h,const uint8_t*k,int len,int u,uint32_t*ix){size_t x=hsh(k,len,u)&(h->M-1);for(;;){E*e=&h->T[x];if(e->gen!=h->gen){e->gen=h->gen;e->len=len;e->u=u;memcpy(e->k,k,len);e->c[0]=e->c[1]=0;*ix=x;ulog(h,x,e->c,1);return e->c;}if(e->len==len&&e->u==u&&!memcmp(e->k,k,len)){*ix=x;return e->c;}x=(x+1)&(h->M-1);}}
static double feed(H*h,const uint8_t*D,long nd,int count){
  double bits=0; int no=h->no;
  for(long q=0;q<nd;q++){
    long i=h->nh; if(h->nh>=h->caph)return -1; h->hist[h->nh++]=D[q]; const uint8_t*B=h->hist;
    int byte=D[q],u=1; const uint8_t*ks[32]; int ls[32];
    for(int w=0;w<no;w++){long L=h->O[w]<i?h->O[w]:i; const uint8_t*s=B+i-L; while(L&&*s==0){s++;L--;} ks[w]=s; ls[w]=(int)L;}
    for(int j=0;j<8;j++){
      uint32_t*g[32]; uint32_t ix[32];
      for(int w=0;w<no;w++) g[w]=look(h,ks[w],ls[w],u,&ix[w]);
      uint64_t p[2];
      for(int y=0;y<2;y++){uint64_t s=1;for(int w=0;w<no;w++)s+=(uint64_t)g[w][y]<<(w+(g[w][1-y]<1));p[y]=s;}
      int y=byte>>(7-j)&1;
      if(count) bits-=log2((double)p[y]/(double)(p[0]+p[1]));
      for(int w=0;w<no;w++){ulog(h,ix[w],g[w],0);uint32_t a=g[w][y],b=g[w][1-y],nb=b/4+2;g[w][y]=a+1;g[w][1-y]=b<nb?b:nb;}
      u=2*u+y;
    }
  }
  return bits;}
void cm2_prefix(H*h,const uint8_t*P,long np){h->gen++;h->nh=0;h->nul=0;h->logging=0;feed(h,P,np,0);}
double cm2_try(H*h,const uint8_t*D,long nd){long nh0=h->nh;h->nul=0;h->logging=1;double b=feed(h,D,nd,1);
  for(size_t i=h->nul;i-->0;){U*x=&h->ul[i];E*e=&h->T[x->idx];if(x->fresh)e->gen=0;else{e->c[0]=x->c0;e->c[1]=x->c1;}}
  h->nul=0;h->logging=0;h->nh=nh0;return b;}
double cm2_bits(H*h,const uint8_t*P,long np,const uint8_t*D,long nd){cm2_prefix(h,P,np);return feed(h,D,nd,1);}
