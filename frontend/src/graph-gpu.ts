import type {GraphViewport} from './types'
export interface GpuLine {points:{x:number;y:number}[];color:[number,number,number,number];width:number;dashed?:boolean;dotted?:boolean;arrowStart?:boolean;arrowEnd?:boolean}
const vertex=`#version 300 es
precision highp float;
in vec2 a_position;in vec2 a_offset;in vec4 a_color;in float a_distance;in float a_dash;
uniform vec3 u_view;uniform vec2 u_size;
out vec4 v_color;out float v_distance;out float v_dash;
void main(){vec2 pixel=a_position*u_view.z+u_view.xy+a_offset;
 gl_Position=vec4(pixel.x/u_size.x*2.-1.,1.-pixel.y/u_size.y*2.,0.,1.);
 v_color=a_color;v_distance=a_distance*u_view.z;v_dash=a_dash;}`
const fragment=`#version 300 es
precision mediump float;
in vec4 v_color;in float v_distance;in float v_dash;out vec4 outColor;
void main(){if(v_dash>1.5){if(mod(v_distance,5.)>1.)discard;}else if(v_dash>.5&&mod(v_distance,9.)>5.)discard;outColor=v_color;}`

/** Camera uniforms move an immutable edge mesh. Model/evidence stay outside GL. */
export class GraphGpuLayer {
  private gl:WebGL2RenderingContext|null=null
  private program:WebGLProgram|null=null
  private buffer:WebGLBuffer|null=null
  private vao:WebGLVertexArrayObject|null=null
  private data=new Float32Array(0)
  private origin={x:0,y:0}
  private viewUniform:WebGLUniformLocation|null=null
  private sizeUniform:WebGLUniformLocation|null=null
  private destroyed=false
  private lost=(event:Event)=>{event.preventDefault();this.gl=null;this.canvas.style.display='none';this.changed()}
  private restored=()=>{if(!this.destroyed){this.initialize();this.changed()}}
  constructor(private canvas:HTMLCanvasElement,private changed=()=>{}){
    canvas.addEventListener('webglcontextlost',this.lost);canvas.addEventListener('webglcontextrestored',this.restored)
    this.initialize()
  }
  get available(){return !!this.gl&&!this.destroyed}
  private initialize(){
    let candidate:WebGL2RenderingContext|null=null
    const shaders:WebGLShader[]=[]
    try{
      const gl=this.canvas.getContext('webgl2',{alpha:true,antialias:true,depth:false,stencil:false,preserveDrawingBuffer:false})
      if(!gl)throw Error('WebGL2 unavailable')
      candidate=gl
      const compile=(type:number,source:string)=>{const shader=gl.createShader(type);if(!shader)throw Error('Shader unavailable');shaders.push(shader);gl.shaderSource(shader,source);gl.compileShader(shader);if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw Error('Shader compilation failed');return shader}
      const vs=compile(gl.VERTEX_SHADER,vertex),fs=compile(gl.FRAGMENT_SHADER,fragment),program=gl.createProgram()
      if(!program)throw Error('Program unavailable')
      gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);gl.deleteShader(vs);gl.deleteShader(fs)
      if(!gl.getProgramParameter(program,gl.LINK_STATUS)){gl.deleteProgram(program);throw Error('Program linking failed')}
      this.program=program;this.buffer=gl.createBuffer();this.vao=gl.createVertexArray()
      if(!this.buffer||!this.vao)throw Error('Buffer unavailable')
      gl.bindVertexArray(this.vao);gl.bindBuffer(gl.ARRAY_BUFFER,this.buffer)
      const fields:[string,number,number][]=[['a_position',2,0],['a_offset',2,2],['a_color',4,4],['a_distance',1,8],['a_dash',1,9]]
      for(const [name,size,offset]of fields){const index=gl.getAttribLocation(program,name);gl.enableVertexAttribArray(index);gl.vertexAttribPointer(index,size,gl.FLOAT,false,40,offset*4)}
      gl.bufferData(gl.ARRAY_BUFFER,this.data,gl.DYNAMIC_DRAW)
      this.viewUniform=gl.getUniformLocation(program,'u_view');this.sizeUniform=gl.getUniformLocation(program,'u_size')
      gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);this.gl=gl;this.canvas.style.display=''
    }catch{for(const shader of shaders)candidate?.deleteShader(shader);candidate?.deleteBuffer(this.buffer);candidate?.deleteVertexArray(this.vao);candidate?.deleteProgram(this.program);this.gl=null;this.canvas.style.display='none'}
  }
  setLines(lines:GpuLine[],origin={x:0,y:0}){
    this.origin=origin
    const capacity=lines.reduce((sum,line)=>sum+Math.max(0,line.points.length-1)*6+(line.arrowStart?3:0)+(line.arrowEnd?3:0),0)
    const values=new Float32Array(capacity*10)
    let offset=0
    const put=(point:{x:number;y:number},dx:number,dy:number,line:GpuLine,distance:number,dashed=line.dashed)=>{
      values[offset++]=point.x-origin.x;values[offset++]=point.y-origin.y
      values[offset++]=dx;values[offset++]=dy
      values.set(line.color,offset);offset+=4
      values[offset++]=distance;values[offset++]=dashed?(line.dotted?2:1):0
    }
    const arrow=(tip:{x:number;y:number},from:{x:number;y:number},line:GpuLine)=>{
      const dx=tip.x-from.x,dy=tip.y-from.y,length=Math.hypot(dx,dy)||1,ux=dx/length,uy=dy/length,size=Math.max(6,line.width*3)
      put(tip,0,0,line,0,false);put(tip,-ux*size-uy*size*.52,-uy*size+ux*size*.52,line,0,false);put(tip,-ux*size+uy*size*.52,-uy*size-ux*size*.52,line,0,false)
    }
    for(const line of lines){let distance=0
      for(let index=1;index<line.points.length;index++){
        const a=line.points[index-1],b=line.points[index],dx=b.x-a.x,dy=b.y-a.y,length=Math.hypot(dx,dy)
        if(!length)continue
        const nx=-dy/length*line.width/2,ny=dx/length*line.width/2,next=distance+length
        put(a,nx,ny,line,distance);put(a,-nx,-ny,line,distance);put(b,nx,ny,line,next)
        put(b,nx,ny,line,next);put(a,-nx,-ny,line,distance);put(b,-nx,-ny,line,next);distance=next
      }
      if(line.points.length>1){if(line.arrowEnd)arrow(line.points.at(-1)!,line.points.at(-2)!,line);if(line.arrowStart)arrow(line.points[0],line.points[1],line)}
    }
    this.data=values.subarray(0,offset)
    if(this.gl&&this.buffer){this.gl.bindBuffer(this.gl.ARRAY_BUFFER,this.buffer);this.gl.bufferData(this.gl.ARRAY_BUFFER,this.data,this.gl.DYNAMIC_DRAW)}
  }
  render(view:GraphViewport,width:number,height:number,dpr=1){
    const gl=this.gl;if(!gl||!this.program||!width||!height)return false
    const w=Math.max(1,Math.round(width*dpr)),h=Math.max(1,Math.round(height*dpr))
    if(this.canvas.width!==w||this.canvas.height!==h){this.canvas.width=w;this.canvas.height=h}
    gl.viewport(0,0,w,h);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);gl.useProgram(this.program);gl.bindVertexArray(this.vao)
    gl.uniform3f(this.viewUniform,view.x+this.origin.x*view.scale,view.y+this.origin.y*view.scale,view.scale);gl.uniform2f(this.sizeUniform,width,height)
    gl.drawArrays(gl.TRIANGLES,0,this.data.length/10);return true
  }
  dispose(){
    this.destroyed=true;this.canvas.removeEventListener('webglcontextlost',this.lost);this.canvas.removeEventListener('webglcontextrestored',this.restored)
    const gl=this.gl;if(gl){gl.deleteBuffer(this.buffer);gl.deleteVertexArray(this.vao);gl.deleteProgram(this.program);gl.getExtension('WEBGL_lose_context')?.loseContext()}
    this.gl=null;this.data=new Float32Array(0);this.canvas.style.display='none'
  }
}
