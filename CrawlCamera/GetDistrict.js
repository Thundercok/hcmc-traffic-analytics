const { default: axios } = require("axios");
const fs = require("fs");
const ListCamera = require("./ListCamera.json");
const ListDistrict = require("./GenLocationWithCoordinates.json");
// let clone = ListCamera.slice(0, ListCamera.length);
// const OPENCAGE_API_KEY = "";

// var count = 0;
// let listLocation = ListDistrict;
// async function getDistrict(lat, lon, id) {
//   const url = `https://api.opencagedata.com/geocode/v1/json?q=${lat}+${lon}&key=${OPENCAGE_API_KEY}&language=vi`;
//   console.log(url);

//   const res = await axios.get(url, { timeout: 10000 });
//   const components = res.data.results[0]?.components;
//   listLocation.push({ ...components, id: id });
//   fs.writeFileSync(
//     "./ListDistrictViaId.json",
//     JSON.stringify(listLocation, null, 2)
//   );
//   return;
// }
// function delay(ms) {
//   return new Promise((resolve) => setTimeout(resolve, ms));
// }

// async function processCameras() {
//   for (const cam of clone) {
//     const { lon, lat } = cam.coordinates;
//     console.log(`Đang xử lý camera ID ${cam.id}...`);
//     count++;
//     getDistrict(lat, lon, cam.id);
//     await delay(1000);
//   }
//   return;
// }

//processCameras();
let output = [];
const generateDistricts = () => {
  const districts = ListCamera.map((cam) => {
    let location = ListDistrict.find((loc) => loc.id === cam.id);

    let district;
    if (location.suburb?.includes("Quận")) {
      district = location.suburb;
    } else if (location.city?.includes("Thủ Đức")) {
      district = location.city;
    } else if (location.city_district?.includes("Huyện")) {
      district = location.city_district;
    } else if (location.state?.includes("Tỉnh")) {
      district = location.state;
    }
    if (!district) {
      console.log(cam.id, location);
    }
    //console.log(`Camera ID: ${cam.id}, District: ${district || "Unknown"}`);
    output.push({
      ...cam,
      district: district,
    });
  });
  fs.writeFileSync(
    "./ListCamerasWithDistrict.json",
    JSON.stringify(output, null, 2)
  );
};
generateDistricts();
