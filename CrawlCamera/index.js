const listCameras = require("./ListCamerasWithDistrict.json");
const fs = require("fs");
const { fork } = require("child_process");

const activeChildren = new Map();

// Lọc ra camera theo quận
const data = listCameras.filter(
  (cam) => cam.district && cam.district == "Quận 7"
);

fs.mkdirSync("./images", { recursive: true });

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const MAX_RESTARTS = 50;
const BASE_DELAY_MS = 2000;
const MAX_DELAY_MS = 60000;

function runChild(cam, restartCount = 0) {
  const child = fork("./crawl.js", [cam.id]);
  activeChildren.set(child.pid, child);

  child.on("exit", async (code, signal) => {
    console.log(
      `⚠️ Child ${child.pid} đã thoát | code: ${code}, signal: ${signal}`
    );
    activeChildren.delete(child.pid);

    if (restartCount >= MAX_RESTARTS) {
      console.error(`💀 Cam ${cam.id} đã restart ${MAX_RESTARTS} lần, dừng hẳn.`);
      return;
    }

    // Exponential backoff: 2s, 4s, 8s, ... capped at 60s
    const backoff = Math.min(BASE_DELAY_MS * Math.pow(2, restartCount), MAX_DELAY_MS);
    console.log(`🔄 Restart cam ${cam.id} sau ${backoff / 1000}s (lần ${restartCount + 1}/${MAX_RESTARTS})`);
    await delay(backoff);
    runChild(cam, restartCount + 1);
  });

  child.on("message", (msg) => {
    console.log("👶 ", msg);
  });
}

(async () => {
  for (const cam of data) {
    runChild(cam);
    await delay(1000);
  }
})();

setInterval(() => {
  console.log(`📈 Hiện tại có ${activeChildren.size} child đang online`);
}, 8000);
