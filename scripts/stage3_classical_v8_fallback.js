"use strict";
/* Research-only, source-free Node/V8-compatible Stage3 directed graph analytics.
 * Runs only within an authorized private computation context. No network access,
 * external data transmission, or private publication. Outputs summaries ONLY.
 * Pure JavaScript ZIP_STORED/gzip DEFLATE parser; immutable original source
 * must be validated by caller against its separately accepted SHA256.
 */
const N = 57204;
function part(s,start,len){
 const a=Math.floor(start/3)*3,z=Math.ceil((start+len)/3)*3,ss=s.slice(a/3*4,z/3*4);
 const map=new Uint8Array(128),cs="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
 for(let i=0;i<64;i++)map[cs.charCodeAt(i)]=i;
 const b=new Uint8Array(ss.length/4*3);let k=0;
 for(let i=0;i<ss.length;i+=4){
  const n=(map[ss.charCodeAt(i)]<<18)|(map[ss.charCodeAt(i+1)]<<12)|(map[ss.charCodeAt(i+2)]<<6)|map[ss.charCodeAt(i+3)];
  b[k++]=n>>>16;b[k++]=n>>>8&255;b[k++]=n&255;
 }
 return b.subarray(start-a,start-a+len);
}
const u32=(b,i)=>(b[i]|b[i+1]<<8|b[i+2]<<16|b[i+3]<<24)>>>0;
const u16=(b,i)=>b[i]|b[i+1]<<8;
function getZipMembers(s,byteLen){
 const taillen=Math.min(byteLen,65557),tail=part(s,byteLen-taillen,taillen);
 let e=-1;for(let i=tail.length-22;i>=0;i--)if(u32(tail,i)===0x06054b50){e=i;break}
 if(e<0)throw Error("EOCD not found");
 const count=u16(tail,e+10),offset=u32(tail,e+16),size=u32(tail,e+12),cd=part(s,offset,size);
 let p=0,out={};
 for(let i=0;i<count;i++){
  if(u32(cd,p)!==0x02014b50)throw Error("Central directory corruption");
  const namelen=u16(cd,p+28),extra=u16(cd,p+30),comment=u16(cd,p+32),local=u32(cd,p+42),method=u16(cd,p+10);
  let name="";for(let j=p+46;j<p+46+namelen;j++)name+=String.fromCharCode(cd[j]);
  const header=part(s,local,30);
  if(u32(header,0)!==0x04034b50)throw Error("Local header corruption");
  const start=local+30+u16(header,26)+u16(header,28);
  out[name]={start,size:u32(cd,p+20),uncompressed:u32(cd,p+24),zipCrc:u32(cd,p+16),method};
  p+=46+namelen+extra+comment;
 }
 return out;
}
function rev(n,len){let x=0;for(let i=0;i<len;i++){x=x<<1|n&1;n>>>=1}return x}
function huff(lengths){
 let mx=0;for(const l of lengths)if(l>mx)mx=l;
 const counts=new Uint16Array(mx+1),next=new Uint16Array(mx+1);
 for(const l of lengths)if(l)counts[l]++;
 let code=0;for(let i=1;i<=mx;i++){code=(code+counts[i-1])*2;next[i]=code}
 const table=new Uint32Array(1<<mx);
 for(let i=0;i<lengths.length;i++){const n=lengths[i];if(!n)continue;const c=rev(next[n]++,n),v=n<<16|i;for(let j=c;j<table.length;j+=1<<n)table[j]=v}
 return {table,mask:(1<<mx)-1,mx};
}
const LB=[3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258];
const LE=[0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0];
const DB=[1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577];
const DE=[0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13];
function gunzip(gz){
 if(gz[0]!==31||gz[1]!==139||gz[2]!==8||gz[3]!==0)throw Error("unsupported gzip header");
 const sz=u32(gz,gz.length-4),out=new Uint8Array(sz);
 let pos=10,bit=0,hold=0,op=0;
 function read(n){while(bit<n){if(pos>=gz.length)throw Error("truncated deflate");hold|=gz[pos++]<<bit;bit+=8}const v=hold&((1<<n)-1);hold>>>=n;bit-=n;return v}
 function sym(h){while(bit<h.mx&&pos<gz.length){hold|=gz[pos++]<<bit;bit+=8}const v=h.table[hold&h.mask],n=v>>>16;if(!n||n>bit)throw Error("bad huffman code");hold>>>=n;bit-=n;return v&65535}
 let done=0;
 do{
  done=read(1);const type=read(2);
  if(type===0){read(bit%8);const len=read(16),nlen=read(16);if((len^nlen)!==65535)throw Error("bad stored block");for(let i=0;i<len;i++)out[op++]=read(8);continue}
  if(type===3)throw Error("invalid DEFLATE block");
  let lit,dist;
  if(type===1){const ll=new Uint8Array(288).fill(8);ll.fill(9,144,256);ll.fill(7,256,280);ll.fill(8,280);lit=huff(ll);dist=huff(new Uint8Array(32).fill(5))}
  else{
   const nlit=read(5)+257,ndist=read(5)+1,ncode=read(4)+4,order=[16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15],clen=new Uint8Array(19);
   for(let i=0;i<ncode;i++)clen[order[i]]=read(3);
   const ch=huff(clen),lens=new Uint8Array(nlit+ndist);let ix=0;
   while(ix<lens.length){
    const v=sym(ch);
    if(v<=15)lens[ix++]=v;
    else if(v===16){if(!ix)throw Error("repeat without prior");const n=read(2)+3,prev=lens[ix-1];for(let i=0;i<n;i++)lens[ix++]=prev}
    else if(v===17)ix+=read(3)+3;
    else if(v===18)ix+=read(7)+11;
    else throw Error("invalid repeat");
   }
   if(ix!==lens.length)throw Error("invalid code lengths");
   lit=huff(lens.subarray(0,nlit));dist=huff(lens.subarray(nlit));
  }
  while(true){
   const v=sym(lit);
   if(v<256){if(op>=sz)throw Error("output overflow");out[op++]=v;continue}
   if(v===256)break;
   const li=v-257;if(li<0||li>=LB.length)throw Error("invalid match");
   const length=LB[li]+read(LE[li]),dc=sym(dist);
   if(dc>=DB.length)throw Error("invalid distance");
   const distance=DB[dc]+read(DE[dc]);if(distance>op)throw Error("negative reference");
   for(let i=0;i<length;i++){if(op>=sz)throw Error("output overflow");out[op]=out[op-distance];op++}
  }
 }while(!done);
 if(op!==sz)throw Error("uncompressed length mismatch");
 const tbl=new Uint32Array(256);for(let n=0;n<256;n++){let x=n;for(let k=0;k<8;k++)x=x>>>1^((x&1)?0xedb88320:0);tbl[n]=x>>>0}
 let crc=0xffffffff;for(let i=0;i<op;i++)crc=tbl[(crc^out[i])&255]^crc>>>8;
 if(((crc^0xffffffff)>>>0)!==u32(gz,gz.length-8))throw Error("gzip CRC check failed");
 return out;
}
function textLines(buf,fn){
 let start=0;
 for(let i=0;i<buf.length;i++)if(buf[i]===10){
  if(i>start){
   let line="";for(let j=start;j<i;j++)line+=String.fromCharCode(buf[j]);
   fn(JSON.parse(line));
  }start=i+1;
 }
 if(start!==buf.length)throw Error("Truncated JSONL");
}
function loadGraphFromB64(s,byteLen){
 const members=getZipMembers(s,byteLen);
 const unzipMember=name=>{
  const m=members[name];if(!m||m.method!==0)throw Error("not ZIP_STORED member: "+name);
  return gunzip(part(s,m.start,m.size));
 };
 const mapping=new Map(),indices=new Set();
 textLines(unzipMember("node2vec_node_mapping.private.jsonl.gz"),row=>{
  if(mapping.has(row.article_id)||indices.has(row.node_index))throw Error("duplicate mapping");
  mapping.set(row.article_id,row.node_index);indices.add(row.node_index);
 });
 if(mapping.size!==N)throw Error("wrong roster "+mapping.size);
 const outgoing=Array.from({length:N},()=>[]),incoming=Array.from({length:N},()=>[]),seen=new Set();
 let raw=0,excluded=0,loops=0;
 textLines(unzipMember("directed_edges.private.jsonl.gz"),row=>{
  raw++;
  const a=mapping.get(row.source_article_id),b=mapping.get(row.target_article_id);
  if(a===undefined||b===undefined){excluded++;return}
  if(a===b){loops++;return}
  const key=a*N+b;if(seen.has(key))throw Error("duplicate directed edge");
  seen.add(key);outgoing[a].push(b);incoming[b].push(a);
 });
 if(raw!==328383||excluded!==47||loops!==29||seen.size!==328307)throw Error("frozen directed edge census mismatch");
 return {outgoing,incoming,census:{raw,excluded,loops,eligible_directed:seen.size,article_count:mapping.size,graph_source:"frozen-original-directed-exact-DOI"}};
}
function analyze(name,neighborhoods){
 let incidences=0;
 for(const g of neighborhoods){const n=g.length;incidences+=n*(n-1)/2}
 const pairs=new Uint32Array(incidences);let t=0;
 for(const g of neighborhoods)for(let i=0;i<g.length;i++)for(let j=i+1;j<g.length;j++){
  const a=g[i],b=g[j];pairs[t++]=(a<b?a*N+b:b*N+a)>>>0;
 }
 if(t!==incidences)throw Error("incidence miscount");
 pairs.sort();
 const histogram=[0,0,0,0,0,0,0],degree=new Uint32Array(N),weighted=new Uint32Array(N);
 const thresholds=[1,2,5],results=thresholds.map(_=>({parent:new Int32Array(N),size:new Int32Array(N),count:0}));
 for(const d of results){for(let i=0;i<N;i++){d.parent[i]=i;d.size[i]=1}}
 function root(d,v){let p=v;while(d.parent[p]!==p){d.parent[p]=d.parent[d.parent[p]];p=d.parent[p]}return p}
 function union(d,a,b){let x=root(d,a),y=root(d,b);if(x!==y){if(d.size[x]<d.size[y]){const q=x;x=y;y=q}d.parent[y]=x;d.size[x]+=d.size[y]}}
 const covered=results.map(_=>new Uint8Array(N));
 let weightSum=0,unique=0,max=0,positive=0,atLeastTwo=0;
 for(let i=0;i<pairs.length;){
  const key=pairs[i];let j=i+1;while(j<pairs.length&&pairs[j]===key)j++;
  const w=j-i,a=Math.floor(key/N),b=key%N;if(!(a<b&&b<N))throw Error("noncanonical projection pair");
  if(w>max)max=w;weightSum+=w;unique++;histogram[Math.min(6,w)]++;
  degree[a]++;degree[b]++;weighted[a]+=w;weighted[b]+=w;
  for(let k=0;k<thresholds.length;k++)if(w>=thresholds[k]){union(results[k],a,b);covered[k][a]=1;covered[k][b]=1;results[k].count++}
  i=j;
 }
 if(weightSum!==incidences)throw Error("weights do not sum to incidences");
 const sensitivity=thresholds.map((thr,i)=>{
  const d=results[i],c=covered[i],sizes=new Map();let nodes=0;
  for(let j=0;j<N;j++)if(c[j]){nodes++;let rt=root(d,j);sizes.set(rt,(sizes.get(rt)||0)+1)}
  let largest=0;for(const value of sizes.values())if(value>largest)largest=value;
  return {min_weight:thr,edges:d.count,covered_articles:nodes,isolates:N-nodes,nontrivial_components:sizes.size,largest_component:largest};
 });
 let maxdegree=0,maxweighted=0,nonzero=0;let degSum=0;
 for(let i=0;i<N;i++){maxdegree=Math.max(maxdegree,degree[i]);maxweighted=Math.max(maxweighted,weighted[i]);degSum+=degree[i];if(degree[i])nonzero++}
 if(degSum!==2*unique)throw Error("degree handshaking mismatch");
 return {name,node_count:N,pair_incidences:incidences,unique_weighted_pairs:unique,max_edge_weight:max,
  weights_histogram:{"1":histogram[1],"2":histogram[2],"3":histogram[3],"4":histogram[4],"5":histogram[5],"6_plus":histogram[6]},
  weighted_sum:weightSum,unweighted_degree_sum:degSum,covered_articles:nonzero,max_unweighted_degree:maxdegree,
  max_weighted_degree:maxweighted,sensitivity};
}
return {loadGraphFromB64,analyze,getZipMembers,part,gunzip};
