(() => {
  const canvas = document.getElementById("heroMacCanvas");
  const status = document.getElementById("hero3d-error");
  const expressionButton = document.getElementById("mac-expression");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  if (!canvas) return;

  if (!window.THREE) {
    status.hidden = false;
    status.textContent = "The 3D preview could not load. Check your connection and refresh.";
    expressionButton.disabled = true;
    console.error("KitVid's 3D preview requires Three.js, but the library did not load.");
    return;
  }

  const THREE = window.THREE;
  let heroScene;
  let heroCamera;
  let heroRenderer;
  let macGroup;
  let cdMesh;
  let slimeGroup;
  let cursorMesh;
  let noteGroup;
  let boltMesh;
  let crtTexture;
  let crtCanvas;
  let crtCtx;
  let blinkTimer = 0;
  let isBlinking = false;
  let macMood = "happy";
  let isDownloading = false;
  let activeDownloadCount = 0;
  let heroDrag = false;
  let heroPrev = { x: 0, y: 0 };
  let heroRotTarget = { x: 0.08, y: -0.28 };
  let heroRotCurrent = { x: 0.08, y: -0.28 };

  function showModelError(message, error) {
    status.hidden = false;
    status.textContent = message;
    expressionButton.disabled = true;
    console.error(message, error);
  }

  function initCrtScreenTexture() {
    crtCanvas = document.createElement("canvas");
    crtCanvas.width = 256;
    crtCanvas.height = 224;
    crtCtx = crtCanvas.getContext("2d");
    crtTexture = new THREE.CanvasTexture(crtCanvas);
    crtTexture.magFilter = THREE.NearestFilter;
    crtTexture.minFilter = THREE.NearestFilter;
    drawCrtFace("happy", false);
  }

  function drawCrtFace(mood, blink) {
    if (!crtCtx) return;
    const ctx = crtCtx;
    ctx.fillStyle = "#181A20";
    ctx.fillRect(0, 0, 256, 224);

    ctx.fillStyle = "rgba(255, 255, 255, 0.04)";
    for (let y = 0; y < 224; y += 6) {
      ctx.fillRect(0, y, 256, 2);
    }

    ctx.fillStyle = "#D4FF2A";

    if (mood === "downloading") {
      drawPixelStar(ctx, 84, 78, 18);
      drawPixelStar(ctx, 168, 78, 18);
      ctx.fillRect(92, 134, 72, 12);
      ctx.fillRect(98, 146, 60, 14);
      ctx.fillRect(108, 160, 40, 10);
    } else if (mood === "sunglasses") {
      ctx.fillStyle = "#FF69C6";
      ctx.fillRect(54, 62, 62, 28);
      ctx.fillRect(140, 62, 62, 28);
      ctx.fillRect(116, 68, 24, 8);
      ctx.fillStyle = "#FFFFFF";
      ctx.fillRect(62, 66, 16, 6);
      ctx.fillRect(148, 66, 16, 6);
      ctx.fillStyle = "#D4FF2A";
      ctx.fillRect(92, 136, 12, 12);
      ctx.fillRect(104, 148, 52, 12);
      ctx.fillRect(156, 136, 12, 12);
    } else {
      ctx.save();
      ctx.translate(128, 112);
      ctx.rotate(-0.14);
      ctx.translate(-128, -112);

      if (blink) {
        ctx.fillRect(82, 78, 24, 8);
        ctx.fillRect(144, 78, 24, 8);
      } else {
        ctx.fillRect(88, 62, 14, 34);
        ctx.fillRect(148, 62, 14, 34);
      }

      ctx.fillRect(76, 126, 14, 14);
      ctx.fillRect(90, 140, 14, 14);
      ctx.fillRect(104, 150, 48, 14);
      ctx.fillRect(152, 140, 14, 14);
      ctx.fillRect(166, 124, 14, 16);
      ctx.restore();
    }

    crtTexture.needsUpdate = true;
  }

  function drawPixelStar(ctx, cx, cy, radius) {
    ctx.fillRect(cx - 4, cy - radius, 8, radius * 2);
    ctx.fillRect(cx - radius, cy - 4, radius * 2, 8);
    ctx.fillRect(cx - radius * 0.6, cy - radius * 0.6, radius * 1.2, radius * 1.2);
  }

  function cycleSmileyExpression() {
    const moods = ["happy", "downloading", "sunglasses"];
    macMood = moods[(moods.indexOf(macMood) + 1) % moods.length];
    isBlinking = false;
    blinkTimer = 0;
    if (!isDownloading) drawCrtFace(macMood, false);
  }

  function initHero3D() {
    const width = canvas.clientWidth || 500;
    const height = canvas.clientHeight || 440;

    heroScene = new THREE.Scene();
    heroCamera = new THREE.PerspectiveCamera(40, width / height, 0.1, 100);
    heroCamera.position.set(0, 0.25, 8.6);

    try {
      heroRenderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    } catch (error) {
      showModelError("The 3D preview could not start because WebGL is unavailable.", error);
      return false;
    }
    heroRenderer.setSize(width, height, false);
    heroRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    const hemi = new THREE.HemisphereLight(0xffffff, 0x8b5cf6, 1.15);
    heroScene.add(hemi);

    const keyLight = new THREE.DirectionalLight(0xffffff, 1.1);
    keyLight.position.set(5, 7, 8);
    heroScene.add(keyLight);

    const pinkRim = new THREE.PointLight(0xff69c6, 1.5, 20);
    pinkRim.position.set(-4, 3, 4);
    heroScene.add(pinkRim);

    macGroup = new THREE.Group();
    heroScene.add(macGroup);

    const lavenderClay = new THREE.MeshStandardMaterial({
      color: 0xd9ceff,
      roughness: 0.35,
      metalness: 0.08,
    });
    const darkerLavender = new THREE.MeshStandardMaterial({
      color: 0xb8a6f5,
      roughness: 0.4,
      metalness: 0.1,
    });

    const headMesh = new THREE.Mesh(new THREE.BoxGeometry(3.1, 2.75, 2.5), lavenderClay);
    headMesh.position.set(0.15, 0.55, 0);
    macGroup.add(headMesh);

    const bezelMesh = new THREE.Mesh(new THREE.BoxGeometry(2.75, 2.35, 0.28), darkerLavender);
    bezelMesh.position.set(0.15, 0.58, 1.24);
    macGroup.add(bezelMesh);

    const screenMesh = new THREE.Mesh(
      new THREE.PlaneGeometry(2.25, 1.9),
      new THREE.MeshBasicMaterial({ map: crtTexture }),
    );
    screenMesh.position.set(0.15, 0.58, 1.39);
    macGroup.add(screenMesh);

    const baseMesh = new THREE.Mesh(new THREE.BoxGeometry(3.25, 0.95, 2.85), lavenderClay);
    baseMesh.position.set(0.15, -1.25, 0.22);
    macGroup.add(baseMesh);

    const lcdCanvas = document.createElement("canvas");
    lcdCanvas.width = 256;
    lcdCanvas.height = 64;
    const lcdContext = lcdCanvas.getContext("2d");
    lcdContext.fillStyle = "#A7F3D0";
    lcdContext.fillRect(0, 0, 256, 64);
    lcdContext.fillStyle = "#064E3B";
    lcdContext.font = "bold 34px monospace";
    lcdContext.fillText("kitvid_v2", 28, 44);

    const lcdMesh = new THREE.Mesh(
      new THREE.BoxGeometry(1.55, 0.42, 0.12),
      new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(lcdCanvas) }),
    );
    lcdMesh.position.set(0.35, -1.08, 1.64);
    macGroup.add(lcdMesh);

    const slotMesh = new THREE.Mesh(
      new THREE.BoxGeometry(1.3, 0.08, 0.1),
      new THREE.MeshStandardMaterial({ color: 0x334155 }),
    );
    slotMesh.position.set(0.35, -1.42, 1.64);
    macGroup.add(slotMesh);

    slimeGroup = new THREE.Group();
    const slimeMat = new THREE.MeshPhysicalMaterial({
      color: 0xff47b6,
      emissive: 0x590938,
      roughness: 0.12,
      metalness: 0.1,
      clearcoat: 1,
      clearcoatRoughness: 0.08,
    });

    const swirl1 = new THREE.Mesh(
      new THREE.TorusGeometry(1.75, 0.22, 20, 64, Math.PI * 1.35),
      slimeMat,
    );
    swirl1.position.set(0.1, -0.7, 0.3);
    swirl1.rotation.set(1.2, 0.3, -0.4);
    slimeGroup.add(swirl1);

    const swirl2 = new THREE.Mesh(new THREE.TorusKnotGeometry(0.65, 0.16, 64, 16, 2, 3), slimeMat);
    swirl2.position.set(0.15, 2.15, 0.1);
    slimeGroup.add(swirl2);

    const dropPositions = [[-1.55, 0.2, 1.1], [1.75, -0.6, 1.2], [-1.3, -1.3, 1.4]];
    dropPositions.forEach(([x, y, z]) => {
      const drop = new THREE.Mesh(new THREE.SphereGeometry(0.24, 20, 20), slimeMat);
      drop.position.set(x, y, z);
      drop.scale.set(1, 1.25, 0.9);
      slimeGroup.add(drop);
    });
    macGroup.add(slimeGroup);

    const cdCanvas = document.createElement("canvas");
    cdCanvas.width = 256;
    cdCanvas.height = 256;
    const cdContext = cdCanvas.getContext("2d");
    const gradient = cdContext.createConicGradient(0, 128, 128);
    gradient.addColorStop(0, "#E0F2FE");
    gradient.addColorStop(0.2, "#F472B6");
    gradient.addColorStop(0.4, "#D4FF2A");
    gradient.addColorStop(0.6, "#818CF8");
    gradient.addColorStop(0.8, "#38BDF8");
    gradient.addColorStop(1, "#E0F2FE");
    cdContext.fillStyle = gradient;
    cdContext.beginPath();
    cdContext.arc(128, 128, 124, 0, Math.PI * 2);
    cdContext.fill();
    cdContext.globalCompositeOperation = "destination-out";
    cdContext.beginPath();
    cdContext.arc(128, 128, 34, 0, Math.PI * 2);
    cdContext.fill();
    cdContext.globalCompositeOperation = "source-over";
    cdContext.strokeStyle = "#111318";
    cdContext.lineWidth = 4;
    cdContext.beginPath();
    cdContext.arc(128, 128, 122, 0, Math.PI * 2);
    cdContext.stroke();

    const cdGeometry = new THREE.CylinderGeometry(1.05, 1.05, 0.05, 48);
    cdGeometry.rotateX(Math.PI / 2);
    cdMesh = new THREE.Mesh(
      cdGeometry,
      new THREE.MeshStandardMaterial({
        map: new THREE.CanvasTexture(cdCanvas),
        metalness: 0.75,
        roughness: 0.18,
      }),
    );
    cdMesh.position.set(-1.35, -1.05, 1.65);
    macGroup.add(cdMesh);

    noteGroup = new THREE.Group();
    const noteMat = new THREE.MeshStandardMaterial({ color: 0xfb7185, roughness: 0.25 });
    const head1 = new THREE.Mesh(new THREE.SphereGeometry(0.22, 16, 16), noteMat);
    const head2 = new THREE.Mesh(new THREE.SphereGeometry(0.22, 16, 16), noteMat);
    head2.position.set(0.48, 0.12, 0);
    const stem1 = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.75, 12), noteMat);
    stem1.position.set(0.14, 0.35, 0);
    const stem2 = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.75, 12), noteMat);
    stem2.position.set(0.62, 0.47, 0);
    const bar = new THREE.Mesh(new THREE.BoxGeometry(0.56, 0.14, 0.1), noteMat);
    bar.position.set(0.38, 0.75, 0);
    bar.rotation.z = 0.24;
    noteGroup.add(head1, head2, stem1, stem2, bar);
    noteGroup.position.set(-1.35, 2.05, 0.6);
    macGroup.add(noteGroup);

    const boltShape = new THREE.Shape();
    boltShape.moveTo(0.1, 0.5);
    boltShape.lineTo(-0.25, 0);
    boltShape.lineTo(0.02, 0);
    boltShape.lineTo(-0.15, -0.5);
    boltShape.lineTo(0.28, 0.08);
    boltShape.lineTo(0.02, 0.08);
    boltShape.closePath();
    const boltGeometry = new THREE.ExtrudeGeometry(boltShape, {
      depth: 0.16,
      bevelEnabled: true,
      bevelSize: 0.03,
      bevelThickness: 0.03,
    });
    boltMesh = new THREE.Mesh(
      boltGeometry,
      new THREE.MeshStandardMaterial({ color: 0xfacc15, roughness: 0.25 }),
    );
    boltMesh.position.set(2.15, 1.35, 0.6);
    macGroup.add(boltMesh);

    const cursorShape = new THREE.Shape();
    cursorShape.moveTo(0, 0.55);
    cursorShape.lineTo(-0.35, -0.35);
    cursorShape.lineTo(-0.08, -0.22);
    cursorShape.lineTo(0.05, -0.52);
    cursorShape.lineTo(0.2, -0.45);
    cursorShape.lineTo(0.07, -0.15);
    cursorShape.lineTo(0.35, -0.15);
    cursorShape.closePath();
    const cursorGeometry = new THREE.ExtrudeGeometry(cursorShape, {
      depth: 0.18,
      bevelEnabled: true,
      bevelSize: 0.03,
      bevelThickness: 0.03,
    });
    cursorMesh = new THREE.Mesh(
      cursorGeometry,
      new THREE.MeshStandardMaterial({ color: 0xe2e8f0, metalness: 0.85, roughness: 0.15 }),
    );
    cursorMesh.position.set(1.55, -1.55, 1.85);
    cursorMesh.rotation.z = 0.35;
    macGroup.add(cursorMesh);

    canvas.addEventListener("mousedown", (event) => {
      heroDrag = true;
      heroPrev = { x: event.clientX, y: event.clientY };
    });
    window.addEventListener("mouseup", () => {
      heroDrag = false;
    });
    window.addEventListener("mousemove", (event) => {
      if (!heroDrag) return;
      const dx = event.clientX - heroPrev.x;
      const dy = event.clientY - heroPrev.y;
      heroRotTarget.y += dx * 0.01;
      heroRotTarget.x = Math.max(-0.6, Math.min(0.6, heroRotTarget.x + dy * 0.01));
      heroPrev = { x: event.clientX, y: event.clientY };
    });

    canvas.addEventListener("touchstart", (event) => {
      if (event.touches.length === 1) {
        heroDrag = true;
        heroPrev = { x: event.touches[0].clientX, y: event.touches[0].clientY };
      }
    }, { passive: true });
    window.addEventListener("touchend", () => {
      heroDrag = false;
    });
    window.addEventListener("touchmove", (event) => {
      if (!heroDrag || event.touches.length !== 1) return;
      const dx = event.touches[0].clientX - heroPrev.x;
      const dy = event.touches[0].clientY - heroPrev.y;
      heroRotTarget.y += dx * 0.012;
      heroRotTarget.x = Math.max(-0.6, Math.min(0.6, heroRotTarget.x + dy * 0.012));
      heroPrev = { x: event.touches[0].clientX, y: event.touches[0].clientY };
    }, { passive: true });

    canvas.addEventListener("keydown", (event) => {
      const step = 0.12;
      if (event.key === "ArrowLeft") heroRotTarget.y -= step;
      else if (event.key === "ArrowRight") heroRotTarget.y += step;
      else if (event.key === "ArrowUp") heroRotTarget.x = Math.max(-0.6, heroRotTarget.x - step);
      else if (event.key === "ArrowDown") heroRotTarget.x = Math.min(0.6, heroRotTarget.x + step);
      else return;
      event.preventDefault();
    });

    expressionButton.addEventListener("click", cycleSmileyExpression);
    return true;
  }

  function syncDownloadState() {
    const activeCount = document.querySelectorAll('.job-item[data-status="running"]').length;
    if (activeCount === activeDownloadCount) return;

    activeDownloadCount = activeCount;
    const downloading = activeCount > 0;
    if (downloading !== isDownloading) {
      isDownloading = downloading;
      isBlinking = false;
      blinkTimer = 0;
      drawCrtFace(isDownloading ? "downloading" : macMood, false);
    }

    renderHero3D(performance.now() * 0.001);
  }

  function animateHero3D() {
    if (reducedMotion.matches) return;
    requestAnimationFrame(animateHero3D);
    const time = performance.now() * 0.001;
    renderHero3D(time);
  }

  function renderHero3D(time) {
    const activity = Math.min(activeDownloadCount, 4);
    const motionScale = reducedMotion.matches ? 0 : 1;
    blinkTimer += 0.016;
    if (!reducedMotion.matches && !isDownloading && macMood === "happy") {
      if (!isBlinking && blinkTimer > 3.6) {
        isBlinking = true;
        drawCrtFace("happy", true);
      } else if (isBlinking && blinkTimer > 3.78) {
        isBlinking = false;
        blinkTimer = 0;
        drawCrtFace("happy", false);
      }
    }

    if (heroRenderer && heroScene && heroCamera && macGroup) {
      if (!heroDrag && motionScale) {
        const rotationSpeed = 0.9 + activity * 0.22;
        const rotationAmount = 0.14 + activity * 0.035;
        heroRotTarget.y = -0.28 + Math.sin(time * rotationSpeed) * rotationAmount;
        heroRotTarget.x = 0.08 + Math.cos(time * (0.7 + activity * 0.16)) * (0.05 + activity * 0.02);
      }
      heroRotCurrent.x += (heroRotTarget.x - heroRotCurrent.x) * 0.08;
      heroRotCurrent.y += (heroRotTarget.y - heroRotCurrent.y) * 0.08;

      macGroup.rotation.x = heroRotCurrent.x;
      macGroup.rotation.y = heroRotCurrent.y;
      macGroup.position.y = Math.sin(time * (1.6 + activity * 0.7)) * (0.12 + activity * 0.025) * motionScale;

      if (cdMesh && motionScale) cdMesh.rotation.z -= 0.025 + activity * 0.065;
      if (slimeGroup) {
        slimeGroup.rotation.y = motionScale ? Math.sin(time * (1.2 + activity)) * activity * 0.08 : 0;
        const pulse = motionScale && activity
          ? 1 + Math.sin(time * (4 + activity * 1.5)) * (0.025 + activity * 0.008)
          : 1;
        slimeGroup.scale.setScalar(pulse);
      }
      if (noteGroup && motionScale) {
        noteGroup.position.y = 2.05 + Math.sin(time * (2.4 + activity * 0.9)) * (0.14 + activity * 0.025);
        noteGroup.rotation.z = Math.sin(time * (1.8 + activity * 0.7)) * (0.15 + activity * 0.04);
      }
      if (boltMesh && motionScale) {
        boltMesh.position.y = 1.35 + Math.cos(time * (2.2 + activity)) * (0.14 + activity * 0.025);
        boltMesh.rotation.z = Math.sin(time * (1.5 + activity)) * activity * 0.08;
      }
      if (cursorMesh && motionScale) {
        cursorMesh.position.y = -1.55 + Math.sin(time * (3 + activity)) * (0.08 + activity * 0.02);
        cursorMesh.rotation.z = 0.35 + Math.sin(time * (2 + activity)) * activity * 0.06;
      }

      heroRenderer.render(heroScene, heroCamera);
    }
  }

  function resizeHero3D() {
    if (!heroCamera || !heroRenderer) return;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (width <= 0 || height <= 0) return;
    heroCamera.aspect = width / height;
    heroCamera.updateProjectionMatrix();
    heroRenderer.setSize(width, height, false);
  }

  initCrtScreenTexture();
  if (initHero3D()) {
    window.addEventListener("resize", resizeHero3D);
    resizeHero3D();
    const downloads = document.getElementById("downloads");
    if (downloads) {
      new MutationObserver(syncDownloadState).observe(downloads, {
        attributes: true,
        attributeFilter: ["data-status"],
        childList: true,
        subtree: true,
      });
    }
    activeDownloadCount = document.querySelectorAll('.job-item[data-status="running"]').length;
    isDownloading = activeDownloadCount > 0;
    if (isDownloading) drawCrtFace("downloading", false);
    animateHero3D();
    if (reducedMotion.matches) renderHero3D(performance.now() * 0.001);
    reducedMotion.addEventListener("change", () => {
      if (reducedMotion.matches) renderHero3D(performance.now() * 0.001);
      else animateHero3D();
    });
  }
})();
