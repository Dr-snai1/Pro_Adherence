"use strict";
/** Research-only Stage3 lossless compact pair representation. Source-free.
 * Binary schema PAC1:
 * magic ASCII PAC1 (4), uint32LE eligible_nodes (4), uint32LE unique_pairs (4),
 * uint32LE weighted_incidence_sum (4), followed by repeated unsigned LEB128
 * delta(key) [initial previous_key=-1] then unsigned LEB128 weight. Keys are
 * strict increasing packed(a*57204+b), a < b, weight>=1. No node/DOI strings.
 * Base64 encoding is only for restricted Drive transport. Exported ASCII
 * fragments join as decoded byte chunks in exact manifest order.
 */
const N=57204;
const enc=(buf)=>{
 let out="";const abc="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
 for(let i=0;i<buf.length;i+=3){
  const x=(buf[i]<<16)|((i+1<buf.length?buf[i+1]:0)<<8)|(i+2<buf.length?buf[i+2]:0);
  out+=abc[x>>>18&63]+abc[x>>>12&63]+(i+1<buf.length?abc[x>>>6&63]:"=")+(i+2<buf.length?abc[x&63]:"=");
 }
 return out;
};
const dec=s=>{
 if(s.length%4)throw Error("base64 length");
 const lookup=new Uint8Array(128);const abc="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
 for(let i=0;i<64;i++)lookup[abc.charCodeAt(i)]=i;
 const pad=s.endsWith("==")?2:s.endsWith("=")?1:0;
 const out=new Uint8Array(s.length/4*3-pad);let p=0;
 for(let i=0;i<s.length;i+=4){
  const x=lookup[s.charCodeAt(i)]<<18|lookup[s.charCodeAt(i+1)]<<12|lookup[s.charCodeAt(i+2)]<<6|lookup[s.charCodeAt(i+3)];
  if(p<out.length)out[p++]=x>>>16;if(p<out.length)out[p++]=x>>>8&255;if(p<out.length)out[p++]=x&255;
 }
 return out;
};
const u32=(buf,p)=> (buf[p]|buf[p+1]<<8|buf[p+2]<<16|buf[p+3]<<24)>>>0;
function crc32(buf){
 const table=new Uint32Array(256);for(let i=0;i<256;i++){let x=i;for(let j=0;j<8;j++)x=(x&1)?x>>>1^0xedb88320:x>>>1;table[i]=x>>>0}
 let crc=0xffffffff;for(let i=0;i<buf.length;i++)crc=(crc>>>8)^table[(crc^buf[i])&255];
 return (crc^0xffffffff)>>>0;
}
function sha256(buf){
 const K=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
 0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
 0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
 0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
 0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
 0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
 0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
 0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
 const H=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
 const n=buf.length,blocks=Math.ceil((n+9)/64),w=new Uint32Array(64);
 for(let block=0;block<blocks;block++){
  const base=block*64;
  for(let i=0;i<16;i++){
   let v=0;for(let j=0;j<4;j++){
    const ix=base+i*4+j;
    const b=ix<n?buf[ix]:ix===n?0x80:ix>=blocks*64-8?Math.floor((n*8)/2**((blocks*64-1-ix)*8))&255:0;
    v=v<<8|b;
   }w[i]=v>>>0;
  }
  for(let i=16;i<64;i++){
   const x=w[i-15],y=w[i-2];
   const s0=(x>>>7|x<<25)^(x>>>18|x<<14)^(x>>>3);
   const s1=(y>>>17|y<<15)^(y>>>19|y<<13)^(y>>>10);
   w[i]=(w[i-16]+s0+w[i-7]+s1)>>>0;
  }
  let [a,b,c,d,e,f,g,h]=H;
  for(let i=0;i<64;i++){
   const S1=(e>>>6|e<<26)^(e>>>11|e<<21)^(e>>>25|e<<7);
   const ch=e&f^~e&g;
   const t1=(h+S1+ch+K[i]+w[i])>>>0;
   const S0=(a>>>2|a<<30)^(a>>>13|a<<19)^(a>>>22|a<<10);
   const maj=a&b^a&c^b&c;
   const t2=(S0+maj)>>>0;
   h=g;g=f;f=e;e=d+t1>>>0;d=c;c=b;b=a;a=t1+t2>>>0;
  }
  H[0]=H[0]+a>>>0;H[1]=H[1]+b>>>0;H[2]=H[2]+c>>>0;H[3]=H[3]+d>>>0;
  H[4]=H[4]+e>>>0;H[5]=H[5]+f>>>0;H[6]=H[6]+g>>>0;H[7]=H[7]+h>>>0;
 }
 return H.map(v=>v.toString(16).padStart(8,"0")).join("");
}
function encodePairs(sortedPairEvents,expectedCount,expectedIncidences){
 if(!sortedPairEvents||typeof sortedPairEvents.length!=="number")throw Error("Sorted pair events required");
 const buffer=new Uint8Array(sortedPairEvents.length*7+16);let pos=0;
 for(const b of [80,65,67,49])buffer[pos++]=b;
 function emitU32(value){for(let i=0;i<4;i++)buffer[pos++]=value>>>i*8&255}
 emitU32(N);emitU32(expectedCount);emitU32(expectedIncidences);
 function varuint(value){if(value<0||value>0xffffffff||!Number.isSafeInteger(value))throw Error("Invalid unsigned varuint");do{let c=value&127;value=Math.floor(value/128);buffer[pos++]=value?c|128:c}while(value)}
 let previous=-1,observed=0,sum=0;
 for(let i=0;i<sortedPairEvents.length;){
  const key=sortedPairEvents[i];let j=i+1;while(j<sortedPairEvents.length&&sortedPairEvents[j]===key)j++;
  const weight=j-i;if(key<=previous||weight<1)throw Error("Unsorted/zero weighted pair");
  varuint(key-previous);varuint(weight);
  previous=key;observed++;sum+=weight;i=j;
 }
 if(observed!==expectedCount||sum!==expectedIncidences)throw Error("Pair count/sum mismatch");
 return buffer.subarray(0,pos);
}
function decodePairCount(bytes){
 if(bytes.length<16||bytes[0]!==80||bytes[1]!==65||bytes[2]!==67||bytes[3]!==49||u32(bytes,4)!==N)throw Error("PAC1 header");
 const declared=u32(bytes,8),inc=u32(bytes,12);let p=16,last=-1,sum=0,n=0;
 const result={declared_unique:declared,declared_incidence_sum:inc,valid_pairs:0,weight_sum:0,max_weight:0,weight_histogram:{"1":0,"2":0,"3":0,"4":0,"5":0,"6_plus":0}};
 function readVar(){let x=0,shift=0;for(let i=0;i<5;i++){if(p>=bytes.length)throw Error("Truncated varuint");let b=bytes[p++];x+=(b&127)*2**shift;if(!(b&128))return x;shift+=7}throw Error("Overlong varuint")}
 while(p<bytes.length){
  const delta=readVar(),w=readVar();const key=last+delta;
  const a=Math.floor(key/N),b=key%N;
  if(delta<1||w<1||key>0xffffffff||!(a>=0&&a<b&&b<N))throw Error("Noncanonical encoded pair");
  n++;sum+=w;last=key;if(w>result.max_weight)result.max_weight=w;
  result.weight_histogram[w<6?String(w):"6_plus"]++;
 }
 if(n!==declared||sum!==inc)throw Error("Decoded pair totals disagree with header");
 result.valid_pairs=n;result.weight_sum=sum;return result;
}
function chunkBytes(bytes,maxChars=400000){
 const chunkSize=Math.floor(maxChars/4)*3;
 if(chunkSize<=0)throw Error("Bad transport size");
 const chunks=[];
 for(let start=0;start<bytes.length;start+=chunkSize){
  const part=bytes.subarray(start,Math.min(start+chunkSize,bytes.length));
  chunks.push({index:chunks.length+1,bytes:part.length,
   sha256:sha256(part),crc32:crc32(part).toString(16).padStart(8,"0"),
   base64:enc(part)});
 }
 return chunks;
}
return {sha256,crc32,enc,dec,encodePairs,decodePairCount,chunkBytes};
