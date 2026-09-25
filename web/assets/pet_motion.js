/* Procedural 2D motion using the existing transparent character poses. */
(function(){
  var classic=document.getElementById("pet"), normal=document.getElementById("avatarCanvas");
  if(!normal && !classic)return;
  if(normal)window.petAnimationV2=true;
  var compat=!!classic, canvas=normal||document.createElement("canvas");
  if(compat){
    canvas.id="petMotionCanvas";
    canvas.style.cssText="position:absolute;inset:0;width:100%;height:100%;pointer-events:none";
    classic.parentNode.insertBefore(canvas,classic);
    classic.style.opacity="0";
  }
  var assets={
    stand:"/assets/yingbao_pose_stand_light.webp",
    wave:"/assets/yingbao_pose_wave_light.webp",
    clasp:"/assets/yingbao_pose_clasp_light.webp"
  }, images={}, wind=0, windGoal=0, windAt=0, blinkAt=performance.now()+2200,
  gestureAt=0, gestureEnd=0, nextGesture=performance.now()+13000, last=0;
  Object.keys(assets).forEach(function(k){
    var im=new Image();im.src=assets[k];im.onload=function(){images[k]=im};
  });
  function basePose(){
    if(compat){
      var src=classic.getAttribute("src")||"";
      return src.indexOf("wave")>=0?"wave":src.indexOf("clasp")>=0?"clasp":"stand";
    }
    return (typeof prefs!=="undefined"&&images[prefs.pose])?prefs.pose:"stand";
  }
  function sleeping(){
    var s=typeof lastState!=="undefined"?lastState:null;
    return !!(s&&s.life&&s.life.sleep_state==="sleeping");
  }
  function trigger(){
    if(sleeping())return;
    gestureAt=performance.now();gestureEnd=gestureAt+1650;
    nextGesture=gestureEnd+14000+Math.random()*10000;
  }
  (compat?classic:document.getElementById("avatar")).addEventListener(
    compat?"click":"pointerup",trigger);
  function smooth(a,b,x){x=Math.max(0,Math.min(1,(x-a)/(b-a)));return x*x*(3-2*x)}
  function drawImage(ctx,img,t,opacity,x,y,w,h){
    if(!img)return;
    var iw=img.naturalWidth,ih=img.naturalHeight,step=20,breath=1+.009*Math.sin(t*.0022);
    ctx.globalAlpha=opacity;
    for(var py=0;py<ih;py+=step){
      var sh=Math.min(step,ih-py),f=(py+sh*.5)/ih;
      var hair=Math.sin(Math.PI*smooth(.02,.60,f))*((wind+Math.sin(t*.0014+f*7)*.8)*smooth(.06,.17,f)*(1-smooth(.54,.68,f)));
      var hem=(wind*.75+Math.sin(t*.0012+f*8)*1.7)*smooth(.55,.80,f);
      var sway=Math.sin(t*.00072)*2.3*(1-smooth(.24,.62,f));
      var bw=(f>.23&&f<.65)?w*breath:w;
      var dx=x+(w-bw)/2+hair+hem+sway;
      var dy=y+f*h-(f>.24&&f<.67?Math.sin(t*.0022)*.5:0);
      ctx.drawImage(img,0,py,iw,sh,dx,dy,bw,h*sh/ih+.35);
    }
    ctx.globalAlpha=1;
  }
  function blink(ctx,t,x,y,w,h){
    if(t>blinkAt+140)blinkAt=t+2600+Math.random()*3400;
    var progress=(t-blinkAt)/140;
    if(progress<0||progress>1)return;
    var closed=Math.sin(progress*Math.PI);
    if(closed<.12)return;
    // Eyelids occupy only the eye pixels; skin shade follows the source art.
    [[.513,.106,1], [.583,.093,-1]].forEach(function(eye){
      var cx=x+eye[0]*w,cy=y+eye[1]*h;
      var rw=w*.021,rh=h*.008*closed;
      ctx.save();ctx.translate(cx,cy);ctx.rotate(eye[2]*-.18);
      ctx.fillStyle="rgba(246,218,217,"+(.92*closed)+")";
      ctx.beginPath();ctx.ellipse(0,0,rw,rh,0,0,Math.PI*2);ctx.fill();
      ctx.strokeStyle="rgba(75,55,66,"+(.82*closed)+")";
      ctx.lineWidth=Math.max(.6,w*.002);
      ctx.beginPath();ctx.moveTo(-rw*.9,0);ctx.quadraticCurveTo(0,rh*.55,rw*.9,-rh*.2);ctx.stroke();
      ctx.restore();
    });
  }
  function frame(t){
    requestAnimationFrame(frame);
    if(document.hidden||t-last<39)return;
    last=t;
    var width=canvas.clientWidth,height=canvas.clientHeight;
    if(!width||!height||!images.stand)return;
    var ratio=Math.min(window.devicePixelRatio||1,2),cw=Math.round(width*ratio),ch=Math.round(height*ratio);
    if(canvas.width!==cw||canvas.height!==ch){canvas.width=cw;canvas.height=ch}
    var ctx=canvas.getContext("2d",{alpha:true});
    ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,width,height);
    ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality="high";
    if(t>windAt){windGoal=(Math.random()*2-1)*1.6;windAt=t+1500+Math.random()*2200}
    wind+=(windGoal-wind)*.045;
    var pose=basePose(),asleep=sleeping();
    if(compat)canvas.style.opacity=asleep?".86":"1";
    if(!asleep&&pose==="stand"&&t>nextGesture){trigger()}
    var showGesture=!asleep&&pose==="stand"&&t<gestureEnd&&t>=gestureAt;
    var opacity=showGesture?
      Math.min(1,smooth(0,250,t-gestureAt),1-smooth(1150,1650,t-gestureAt)):0;
    var aw=Math.min(width*(compat?.86:1),height*2/3),ah=aw*1.5;
    var ax=(width-aw)/2,ay=compat?(height-ah)/2:height-ah;
    drawImage(ctx,images[pose]||images.stand,t,1,ax,ay,aw,ah);
    if(opacity>0)drawImage(ctx,images.wave,t,opacity,ax,ay,aw,ah);
    if(!asleep)blink(ctx,t,ax,ay,aw,ah);
  }
  requestAnimationFrame(frame);
})();
