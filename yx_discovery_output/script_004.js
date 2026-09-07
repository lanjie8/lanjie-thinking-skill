var hostName = location.hostname;
if (hostName == 'localhost') {
	hostName = "https://muyang.hn.cn";
} else {
	hostName = "https://" + hostName;
}

//设备情况
var ua = 'other',
	plat = 'other';
var u = navigator.userAgent;
var isAndroid = u.indexOf('Android') > -1 || u.indexOf('Linux') > -1;
if (isAndroid) {
	ua = 'android';
}
var isiOS = !!u.match(/\(i[^;]+;( U;)? CPU.+Mac OS X/); //ios缁堢
if (isiOS) {
	ua = 'ios';
}
var isQQnews = u.match(/qqnews\/([\.\d ]+)/i);
if (isQQnews) {
	plat = 'newsapp';
}
if (u.toLowerCase().match(/MicroMessenger/i) == 'micromessenger') {
	plat = 'weixin';
}

window.shareData = { // 微信分享词
	"imgUrl": "https://muyang.hn.cn/img/logo.jpg", //分享图片,不填默认是qqlogo
	"tLink": '', //分享的链接, 不填默认是当前页面
	"tTitle": "",
	"tContent": "",
	"timeLine": "",
	"wasShare": function () { }, //分享成功的回调函数
};

function openMap(locationSign, name, address) {
	var location = locationSign.split(',');
	if (plat == 'weixin') {
		wx.openLocation({
			latitude: parseFloat(location[1]), // 纬度，浮点数，范围为90 ~ -90
			longitude: parseFloat(location[0]), // 经度，浮点数，范围为180 ~ -180。
			name: name, // 位置名
			address: address, // 地址详情说明
			scale: 15, // 地图缩放级别,整形值,范围从1~28。默认为最大
			infoUrl: '' // 在查看位置界面底部显示的超链接,可点击跳转
		});
	} else {
		//  	alert('只能在微信中使用');
		window.open('//uri.amap.com/marker?position=' + locationSign + '&name=' + name + address + '&src=qqsj&coordinate=gaode&callnative=1');
	}
}

// 更精确的转换方法（基于官方算法）
function bdToAmapAccurate(bd_lat, bd_lng) {
    // 常量定义
    const x_pi = Math.PI * 3000.0 / 180.0;
    
    // 百度坐标转国测局坐标
    const x = bd_lng - 0.0065;
    const y = bd_lat - 0.006;
    
    // 转换公式
    const z = Math.sqrt(x * x + y * y) - 0.00002 * Math.sin(y * x_pi);
    const theta = Math.atan2(y, x) - 0.000003 * Math.cos(x * x_pi);
    
    const amap_lng = z * Math.cos(theta);
    const amap_lat = z * Math.sin(theta);
	console.log('转高德坐标',amap_lng, amap_lat);
    return {
        lat: amap_lat,
        lng: amap_lng
    };
}

/**
 *  判断经纬度是否超出中国境内
 */
function isLocationOutOfChina(latitude, longitude) {
  if (longitude < 72.004 || longitude > 137.8347 || latitude < 0.8293 || latitude > 55.8271)
    return true;
  return false;
}


/**
 *  将WGS-84(国际标准)转为GCJ-02(火星坐标):
 */
function transformFromWGSToGCJ(latitude, longitude) {
  var lat = "";
  var lon = "";
  var ee = 0.00669342162296594323;
  var a = 6378245.0;
  var pi = 3.14159265358979324;

  if (isLocationOutOfChina(latitude, longitude)) {
    lat = latitude;
    lon = longitude;
  }
  else {
    var adjustLat = transformLatWithXY(longitude - 105.0, latitude - 35.0);
    var adjustLon = transformLonWithXY(longitude - 105.0, latitude - 35.0);
    var radLat = latitude / 180.0 * pi;
    var magic = Math.sin(radLat);
    magic = 1 - ee * magic * magic;
    var sqrtMagic = Math.sqrt(magic);
    adjustLat = (adjustLat * 180.0) / ((a * (1 - ee)) / (magic * sqrtMagic) * pi);
    adjustLon = (adjustLon * 180.0) / (a / sqrtMagic * Math.cos(radLat) * pi);
    latitude = latitude + adjustLat;
    longitude = longitude + adjustLon;
  }
  return { latitude: latitude, longitude: longitude };

}

/**
 *  将GCJ-02(火星坐标)转为百度坐标(DB-09):
 */
function transformFromGCJToBaidu(latitude, longitude) {  
  var pi = 3.14159265358979324 * 3000.0 / 180.0;

  var z = Math.sqrt(longitude * longitude + latitude * latitude) + 0.00002 * Math.sin(latitude * pi);
  var theta = Math.atan2(latitude, longitude) + 0.000003 * Math.cos(longitude * pi);
  var a_latitude = (z * Math.sin(theta) + 0.006);
  var a_longitude = (z * Math.cos(theta) + 0.0065);

  return { latitude: a_latitude, longitude: a_longitude };
}

/**
 *  将百度坐标(DB-09)转为GCJ-02(火星坐标):
 */
function transformFromBaiduToGCJ(latitude, longitude) {
  var xPi = 3.14159265358979323846264338327950288 * 3000.0 / 180.0;

  var x = longitude - 0.0065;
  var y = latitude - 0.006;
  var z = Math.sqrt(x * x + y * y) - 0.00002 * Math.sin(y * xPi);
  var theta = Math.atan2(y, x) - 0.000003 * Math.cos(x * xPi);
  var a_latitude = z * Math.sin(theta);
  var a_longitude = z * Math.cos(theta);

  return { latitude: a_latitude, longitude: a_longitude };
}

/**
 *  将GCJ-02(火星坐标)转为WGS-84(国际标准):
 */
function transformFromGCJToWGS(latitude, longitude) {
  var threshold = 0.00001;

  // The boundary
  var minLat = latitude - 0.5;
  var maxLat = latitude + 0.5;
  var minLng = longitude - 0.5;
  var maxLng = longitude + 0.5;

  var delta = 1;
  var maxIteration = 30;

  while (true) {
    var leftBottom = transformFromWGSToGCJ(minLat, minLng);
    var rightBottom = transformFromWGSToGCJ(minLat, maxLng);
    var leftUp = transformFromWGSToGCJ(maxLat, minLng);
    var midPoint = transformFromWGSToGCJ((minLat + maxLat) / 2, (minLng + maxLng) / 2);
    delta = Math.abs(midPoint.latitude - latitude) + Math.abs(midPoint.longitude - longitude);

    if (maxIteration-- <= 0 || delta <= threshold) {
      return { latitude: (minLat + maxLat) / 2, longitude: (minLng + maxLng) / 2 };
    }

    if (isContains({ latitude: latitude, longitude: longitude }, leftBottom, midPoint)) {
      maxLat = (minLat + maxLat) / 2;
      maxLng = (minLng + maxLng) / 2;
    }
    else if (isContains({ latitude: latitude, longitude: longitude }, rightBottom, midPoint)) {
      maxLat = (minLat + maxLat) / 2;
      minLng = (minLng + maxLng) / 2;
    }
    else if (isContains({ latitude: latitude, longitude: longitude }, leftUp, midPoint)) {
      minLat = (minLat + maxLat) / 2;
      maxLng = (minLng + maxLng) / 2;
    }
    else {
      minLat = (minLat + maxLat) / 2;
      minLng = (minLng + maxLng) / 2;
    }
  }

}

function isContains(point, p1, p2) {
  return (point.latitude >= Math.min(p1.latitude, p2.latitude) && point.latitude <= Math.max(p1.latitude, p2.latitude)) && (point.longitude >= Math.min(p1.longitude, p2.longitude) && point.longitude <= Math.max(p1.longitude, p2.longitude));
}

function transformLatWithXY(x, y) {
  var pi = 3.14159265358979324;
  var lat = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
  lat += (20.0 * Math.sin(6.0 * x * pi) + 20.0 * Math.sin(2.0 * x * pi)) * 2.0 / 3.0;
  lat += (20.0 * Math.sin(y * pi) + 40.0 * Math.sin(y / 3.0 * pi)) * 2.0 / 3.0;
  lat += (160.0 * Math.sin(y / 12.0 * pi) + 320 * Math.sin(y * pi / 30.0)) * 2.0 / 3.0;
  return lat;
}

function transformLonWithXY(x, y) {
  var pi = 3.14159265358979324;
  var lon = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
  lon += (20.0 * Math.sin(6.0 * x * pi) + 20.0 * Math.sin(2.0 * x * pi)) * 2.0 / 3.0;
  lon += (20.0 * Math.sin(x * pi) + 40.0 * Math.sin(x / 3.0 * pi)) * 2.0 / 3.0;
  lon += (150.0 * Math.sin(x / 12.0 * pi) + 300.0 * Math.sin(x / 30.0 * pi)) * 2.0 / 3.0;
  return lon;
}


function getOperator(phoneNum) {
	var head = parseInt(phoneNum.substr(1, 2));
	if (head == 30 || head == 31 || head == 32 || head == 55 || head == 56 || head == 85 || head == 86) {
		return '中国联通';
	} else if (head == 33 || head == 53 || head == 80 || head == 81 || head == 89) {
		return '中国电信';
	} else {
		return '中国移动';
	}
}

function testTel(tel) {
	var reg = /^0?1[2|3|4|5|6|7|8|9][0-9]\d{8}$/;
	if (reg.test(tel)) {
		return true;
	} else {
		return false;
	}
}

function isNumber(nubmer) {
	var re = /^[0-9]+.?[0-9]*$/; //判断字符串是否为数字 //判断正整数 /^[1-9]+[0-9]*]*$/ 
	if (!re.test(nubmer)) {
		return false;
	}
	return true;
}

//富文本编辑器转化
function escape2Html(str) {
	var arrEntities = {
		'lt': '<',
		'gt': '>',
		'nbsp': ' ',
		'amp': '&',
		'quot': '"'
	};
	return str.replace(/&(lt|gt|nbsp|amp|quot);/ig, function (all, t) {
		return arrEntities[t];
	});
}

function formToJson(formQuery) {
	var data = {};
	$(formQuery).serializeArray().map(function (x) {
		if (x.value) {
			data[x.name] = x.value;
		}
	});
	return data;
}

//json转url参数,递归函数
function urlEncode(param, key, encode) {
	if (param == null) return '';
	var paramStr = '';
	var t = typeof (param);
	if (t == 'string' || t == 'number' || t == 'boolean') {
		paramStr += '&' + key + '=' + ((encode == null || encode) ? encodeURIComponent(param) : param);
	} else {
		for (var i in param) {
			var k = key == null ? i : key + (param instanceof Array ? '[' + i + ']' : '.' + i);
			paramStr += urlEncode(param[i], k, encode);
		}
	}
	return paramStr;
};

//有数组数据传给php时使用   把对象数组转成二维数组
function urlToPhp(obj) {

	var urlStr = urlEncode(obj);
	var xb1 = xb2 = urlStr.indexOf('].');
	while (xb1 > 0) {
		xb2 = urlStr.indexOf('=', xb1);
		var xb3 = urlStr.indexOf('[', xb1);
		if (xb2 > xb3 && xb3 != -1) { // 是多维数组且
			xb2 = xb3;
		}
		var tempStr = urlStr.substring(xb1, xb2);
		var tempStr2 = '][' + urlStr.substring(xb1 + 2, xb2) + ']';
		urlStr = urlStr.replace(new RegExp(tempStr, 'gm'), tempStr2);
		xb1 = urlStr.indexOf('].');
	}
	urlStr = urlStr.replace('&', ''); //去掉第一个&符号

	return urlStr;
}

//将url中的参数转换成json格式
function urlToJson() { //默认参数为当前链接
	var url = arguments[0] || window.location.href;
	if (url.indexOf('?') < 0) {
		return false; //不存在参数返回false
	} else {
		var paraString = url.substring(url.indexOf('?') + 1, url.length);

		if (paraString) {
			var paraJsonString;
			paraJsonString = paraString.replace(/\=/g, "\"\:\"");
			paraJsonString = paraJsonString.replace(/\&/g, "\",\"");
			paraJsonString = paraJsonString.replace(/\+/g, " ");
			paraJsonString = paraJsonString.replace(/\%26/g, "&");
			paraJsonString = paraJsonString.replace(/\%2F/g, "\/");
			paraJsonString = paraJsonString.replace(/\%0A/g, "\:");
			paraJsonString = '{"' + paraJsonString + '"}';
			try {
				return JSON.parse(paraJsonString);
			} catch (error) {
				return false;
			}
		} else {
			return false; //不存在参数返回false
		}

	}
}
var urlData = urlToJson();

// 获取表格数据
function getTableData(page) {
	var callback = app.tableCallback || function () { };

	var postData = app.postData;
	if (postData) {
		postData.page = page;
	} else {
		postData = {
			page: page
		};
	}
	app.tableLoading = true;
	app.tableData = [];
	$.post(app.tableUrl, urlToPhp(postData), function (response) {
		console.log(response);
		app.tableLoading = false;
		var lastData = response.pop(); //数据最后一个是总长度
		app.tableLength = lastData.totalCount;
		app.tableData = response;
		callback(response.data);
	}, 'json');
}

function showQRcodeMask(url) {
	$("#mask-qrcode").fadeIn(600);
	qrcode.clear();
	qrcode.makeCode(url);
}

//写cookies 
function setCookie(name, value, hour) {
	hour = hour || 30 * 24;
	var exp = new Date();
	exp.setTime(exp.getTime() + hour * 60 * 60 * 1000);
	document.cookie = name + "=" + escape(value) + ";expires=" + exp.toGMTString() + ';path=/';
	// 作用域全域名,单页则删除  + ';path=/'
	return value;
}

//读取cookies 
// function getCookie(name) {
// 	var arr, reg = new RegExp("(^| )" + name + "=([^;]*)(;|$)");
// 	if (arr = document.cookie.match(reg))
// 		return unescape(arr[2]);
// 	else
// 		return '';
// }

//删除cookie中所有定变量函数    
function delAllCookie() {
	var keys = document.cookie.match(/[^ =;]+(?=\=)/g);
	if (keys) {
		for (var i = keys.length; i--;) {
			document.cookie = keys[i] + '=0;expires=' + new Date(0).toUTCString() + ';path=/';
		}
	}
}

//时间戳转本地日期
function getLocalTime(nS) {
	return new Date(parseInt(nS) * 1000).toLocaleString().replace(/:\d{1,2}$/, ' ');
}

Date.prototype.Format = function (fmt) { //author: meizz 
	var o = {
		"M+": this.getMonth() + 1, //月份 
		"d+": this.getDate(), //日 
		"h+": this.getHours(), //小时 
		"m+": this.getMinutes(), //分 
		"s+": this.getSeconds(), //秒 
		"q+": Math.floor((this.getMonth() + 3) / 3), //季度 
		"S": this.getMilliseconds() //毫秒 
	};
	if (/(y+)/.test(fmt)) fmt = fmt.replace(RegExp.$1, (this.getFullYear() + "").substr(4 - RegExp.$1.length));
	for (var k in o)
		if (new RegExp("(" + k + ")").test(fmt)) fmt = fmt.replace(RegExp.$1, (RegExp.$1.length == 1) ? (o[k]) : (("00" + o[k]).substr(("" + o[k]).length)));
	return fmt;
}

//计算高德坐标两点间的距离(116.368904, 39.923423 , 116.387271, 39.922501)
function calculateLineDistance(x1, y1, x2, y2) {
	var d1 = 0.01745329251994329;
	var d2 = x1;
	var d3 = y1;
	var d4 = x2;
	var d5 = y2;
	d2 *= d1;
	d3 *= d1;
	d4 *= d1;
	d5 *= d1;
	var d6 = Math.sin(d2);
	var d7 = Math.sin(d3);
	var d8 = Math.cos(d2);
	var d9 = Math.cos(d3);
	var d10 = Math.sin(d4);
	var d11 = Math.sin(d5);
	var d12 = Math.cos(d4);
	var d13 = Math.cos(d5);
	var arrayOfDouble1 = [];
	var arrayOfDouble2 = [];
	arrayOfDouble1.push(d9 * d8);
	arrayOfDouble1.push(d9 * d6);
	arrayOfDouble1.push(d7);
	arrayOfDouble2.push(d13 * d12);
	arrayOfDouble2.push(d13 * d10);
	arrayOfDouble2.push(d11);
	var d14 = Math.sqrt((arrayOfDouble1[0] - arrayOfDouble2[0]) * (arrayOfDouble1[0] - arrayOfDouble2[0]) +
		(arrayOfDouble1[1] - arrayOfDouble2[1]) * (arrayOfDouble1[1] - arrayOfDouble2[1]) +
		(arrayOfDouble1[2] - arrayOfDouble2[2]) * (arrayOfDouble1[2] - arrayOfDouble2[2]));

	return (Math.asin(d14 / 2.0) * 12742001.579854401);
}

//描述转时间差  x天x小时x分钟x秒
function secondToDiffer(second) {
	var days = Math.floor(second / (24 * 3600)); //天
	var leave1 = second % (24 * 3600); //计算天数后剩余的秒数  
	var hours = Math.floor(leave1 / 3600);
	var leave2 = leave1 % 3600; //计算小时数后剩余的毫秒数  
	var minutes = Math.floor(leave2 / 60); //计算相差分钟数  
	var leave3 = leave2 % 60; //计算分钟数后剩余的毫秒数  
	var seconds = Math.round(leave3); //计算相差秒数 
	if (days > 0) {
		return days + "天 " + hours + "小时";
	} else if (hours > 0) {
		return hours + "小时  " + minutes + "分钟";
	} else if (minutes > 0) {
		return minutes + "分钟 " + seconds + "秒";
	} else {
		return seconds + "秒";
	}
}

//原生ajaxpost请求
function ajaxPost(url, postData, callback) {
	if (url) {
		postData = postData || {};
		callback = callback || function () { };
		postData = (function (obj) { // 转成post需要的字符串.  
			var str = "";
			for (var prop in obj) {
				str += prop + "=" + obj[prop] + "&"
			}
			return str;
		})(postData);
		var xhr = new XMLHttpRequest();
		xhr.open("POST", url, true);
		xhr.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
		xhr.onreadystatechange = function () {
			var XMLHttpReq = xhr;
			if (XMLHttpReq.readyState == 4) {
				if (XMLHttpReq.status == 200) {
					var text = XMLHttpReq.responseText;
					callback(text);
				}
			}
		};
		xhr.send(postData);
	} else {
		console.log('url不存在');
	}
}

function compressImage(fileDomId, maxW, maxH, callback) { //压缩图片并旋转正确
	callback = callback || function () { };
	var oFile = new FileReader();
	var passFileType = /^(?:image\/bmp|image\/gif|image\/jpeg|image\/png)$/i;
	var canvas; //= document.createElement('canvas');
	var ctx; // = canvas.getContext("2d");
	var img = new Image();
	var _rotate = 0;
	var mx = 0;
	var my = 1;
	var isFrist = true;
	var baseW = maxW || 640;
	var baseH = maxH || 640;
	//测试状态
	var _orientation = 1;

	$("#" + fileDomId).on('change', function (e) {
		if (!e.target || !e.target.files.length || !e.target.files[0]) {
			return
		};
		var _file = e.target.files[0];
		if (!passFileType.test(_file.type)) {
			return
		};

		EXIF.getData(_file, function () {

			var _dataTxt = EXIF.pretty(this);
			var _dataJson = JSON.stringify(EXIF.getAllTags(this));
			_rotate = 0;
			_orientation = EXIF.getTag(this, 'Orientation');
			//获取照片状态
			if (typeof (urlData) != "undefined" && urlData.exif) {
				alert(_orientation);
			}
		});
		oFile.readAsDataURL(_file);
	});

	oFile.onload = function (f) {
		compress(this.result, baseW, baseH, function (data) {
			callback(data);
		});
	};

	function compress(imgData, maxWidth, maxHeight, callback) {
		canvas = document.createElement('canvas');
		ctx = canvas.getContext("2d");
		if (!imgData) {
			return;
		}
		callback = callback || function () { };
		img = new Image()
		img.onload = function () {
			canvas.width = maxWidth; //重置canvans宽高
			canvas.height = maxHeight;
			ctx.clearRect(0, 0, canvas.width, canvas.height); // canvas清屏

			if (_orientation == 3) { //180°
				if (img.height > maxWidth) { //按最大高度等比缩放
					img.height = maxWidth * img.height / img.width;
					img.width = maxWidth;
				}
				canvas.width = img.width; //重置canvans宽高
				canvas.height = img.height;
				_rotate = 180;
				ctx.rotate(_rotate * Math.PI / 180);
				ctx.translate(-1 * img.width, -1 * img.height);
			} else if (_orientation == 6) { //顺时针90°
				if (img.height > maxWidth) { //按最大高度等比缩放
					img.width = maxWidth * img.width / img.height;
					img.height = maxWidth;
				}
				canvas.width = img.height; //重置canvans宽高
				canvas.height = img.width;
				_rotate = 90;
				ctx.rotate(_rotate * Math.PI / 180);
				ctx.translate(0, -1 * maxWidth);
			} else if (_orientation == 8) { //逆时针90°
				if (img.height > maxWidth) { //按最大高度等比缩放
					img.width = maxWidth * img.width / img.height;
					img.height = maxWidth;
				}
				canvas.width = img.height; //重置canvans宽高
				canvas.height = img.width;
				_rotate = 270;
				ctx.rotate(_rotate * Math.PI / 180);
				ctx.translate(-1 * img.width, 0);
			} else { //未旋转
				if (img.width > maxWidth) { //按最大高度等比缩放
					img.height = maxWidth * img.height / img.width;
					img.width = maxWidth;
				}
				canvas.width = img.width; //重置canvans宽高
				canvas.height = img.height;
				_rotate = 0;
				ctx.rotate(0 * Math.PI / 180);
				ctx.translate(0, 0);
			}

			console.log('ori:' + _orientation + '  旋转:' + _rotate + 'imgW:' + img.width + 'imgH:' + img.height);
			ctx.clearRect(0, 0, canvas.width, canvas.height); // canvas清屏

			ctx.drawImage(img, 0, 0, img.width, img.height);
			callback(canvas.toDataURL("image/jpeg", 0.6));
			//必须等压缩完才读取canvas值，否则canvas内容是黑帆布
		};
		// 记住必须先绑定事件，才能设置src属性，否则img没内容可以画到canvas
		img.src = imgData;
	}
}

//百度语音输出
function speckText(str) {
	var url = "http://tts.baidu.com/text2audio?lan=zh&ie=UTF-8&text=" + encodeURI(str); // baidu
	var n = new Audio(url);
	n.src = url;
	n.play();
}

function preloadImages(arr, stepfun, overfun) {
	var newimages = [],
		loadedimages = 0;
	var arr = (typeof arr != "object") ? [arr] : arr;

	function imageloadpost() {
		loadedimages++;
		stepfun && stepfun(loadedimages);
		if (loadedimages == arr.length) {
			console.log("图片已经加载完成");
			overfun && overfun(newimages);
		}
	}
	for (var i = 0; i < arr.length; i++) {
		newimages[i] = new Image();
		newimages[i].src = arr[i];
		newimages[i].onload = function () {
			imageloadpost();
		}
		newimages[i].onerror = function () {
			console.log("第" + i + "张图片加载出现问题");
			imageloadpost();
		}
	}
}

//数组相关
Array.prototype.indexOf = function (val) {
	for (var i = 0; i < this.length; i++) {
		if (this[i] == val) return i;
	}
	return -1;
};
Array.prototype.remove = function (val) {
	var index = this.indexOf(val);
	if (index > -1) {
		this.splice(index, 1);
	}
};

function mobileImg(url, type) {
	type = type || 'mobile';
	if (url && url.indexOf('file.myqcloud') >= 0) {
		url = url.replace('file.myqcloud', 'image.myqcloud');
	}
	if (url && url.indexOf('myqcloud') >= 0) {
		url += '!' + type;
	}
	return url;
}


function canvasTextAutoLine(str, canvas, ctx, initX, initY, initW, lineHeight) {
	var lineWidth = 0;
	var canvasWidth = canvas.width;
	var lastSubStrIndex = 0;
	for (var i = 0; i < str.length; i++) {
		lineWidth += ctx.measureText(str[i]).width;
		if (lineWidth > initW) {//减去initX,防止边界出现的问题
			ctx.fillText(str.substring(lastSubStrIndex, i), initX, initY);
			initY += lineHeight;
			lineWidth = 0;
			lastSubStrIndex = i;
		}
		if (i == str.length - 1) {
			ctx.fillText(str.substring(lastSubStrIndex, i + 1), initX, initY);
		}
	}
}

function randomNum(min, max) {
  return min + Math.floor(Math.random() * (max - min + 1));
};

//时间
var today = {};
var now = new Date();
today.years = now.getFullYear();
today.month = now.getMonth() + 1;
today.days = now.getDate();
today.str = now.Format("yyyy/MM/dd");
today.str1 = now.Format("yyyy-MM-dd");


var wasLoad = "";
var loading = true;





var globalLoading = {
	show: function (time) {
		var globalLoadingDom = document.getElementById('globalLoading');
		if (globalLoadingDom) {
			globalLoadingDom.style.display = 'block';
		} else {
			var div = document.createElement("div");
			div.id = 'globalLoading';
			div.className = 'bigIn';
			div.innerHTML = '<div class="loader"></div>';
			document.body.appendChild(div);
		}
	},
	hide: function () {
		var globalLoadingDom = document.getElementById('globalLoading');
		if (globalLoadingDom) {
			globalLoadingDom.style.display = 'none';
		}
	}
}