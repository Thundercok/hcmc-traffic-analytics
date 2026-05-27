const { default: axios, head } = require("axios");
const { HeaderGenerator } = require("header-generator");
const fs = require("fs");
const crypto = require("crypto");

const genHeader = () => {
  let headerGenerator = new HeaderGenerator({
    browsers: [
      { name: "firefox", minVersion: 80 },
      { name: "chrome", minVersion: 87 },
      "safari",
    ],
    devices: ["desktop"],
    operatingSystems: ["windows"],
  });
  return headerGenerator.getHeaders();
};

const genFileName = async (id) => {
  const now = new Date();

  const day = String(now.getDate()).padStart(2, "0");
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const year = now.getFullYear();

  const hours = String(now.getHours()).padStart(2, "0");
  const minutes = String(now.getMinutes()).padStart(2, "0");
  const seconds = String(now.getSeconds()).padStart(2, "0");

  const filename = `./images/${id}/${hours}-${minutes}-${seconds}_${day}-${month}-${year}_${id}.jpg`;
  return filename;
};

function getHash(buffer) {
  return crypto.createHash("md5").update(buffer).digest("hex");
}

const fetchImage = async (id, interval) => {
  let lastHash = null;
  let count = 0;
  let consecutiveErrors = 0;
  fs.mkdirSync("./images/" + id, { recursive: true });
  try {
    setInterval(async () => {
      try {
        const headers = genHeader();

        const response = await axios.get(
          "https://giaothong.hochiminhcity.gov.vn/render/ImageHandler.ashx?id=" +
            id,
          {
            headers,
            responseType: "arraybuffer",
            timeout: 5000,
          }
        );

        consecutiveErrors = 0; // reset on success
        const currentHash = getHash(response.data);
        if (currentHash !== lastHash) {
          count++;
          lastHash = currentHash;
          const fileName = await genFileName(id);
          process.send?.("Fetched " + count + " 👍:" + fileName);
          fs.writeFileSync(fileName, response.data);
        }
      } catch (error) {
        consecutiveErrors++;
        if (error.code === "ECONNABORTED") {
          console.error(`⏱️ Timeout khi tải ảnh ID: ${id} (${consecutiveErrors}x)`);
        } else if (error.response) {
          console.error(
            `🚫 Server trả về lỗi ${error.response.status} khi tải ảnh ID: ${id}`
          );
        } else {
          console.error(
            `❌ Lỗi không xác định khi tải ảnh ID: ${id}`,
            error.message
          );
        }
        // V-17: Exit after 10 consecutive errors instead of on first error
        if (consecutiveErrors >= 10) {
          console.error(`💀 Quá nhiều lỗi liên tiếp cho ID: ${id}, thoát.`);
          process.exit(1);
        }
      }
    }, interval);
  } catch (error) {
    console.error("😒 (Func) Lỗi khi fetch ảnh:" + id);
    process.exit(1);
  }
};

const id = process.argv[2];

if (!id) {
  process.exit(1);
}

fetchImage(id, 8000);

// fetchImage("56df8381c062921100c143e2", 8000);
