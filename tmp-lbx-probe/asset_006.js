var log = console.log.bind(console);
// var maskOpen = false;

// document.addEventListener('touchmove', function (e) {
// 	if (maskOpen) {

// 	} else {
// 		e.preventDefault();
// 	}
// }, {
// 	passive: false
// });

var wAlert = window.alert;
window.alert = function (message, callback) {
	callback = callback || function () { };
	try {
		var iframe = document.createElement("IFRAME");
		iframe.style.display = "none";
		iframe.setAttribute("src", 'data:text/plain,');
		document.documentElement.appendChild(iframe);
		var alertFrame = window.frames[0];
		var iwindow = alertFrame.window;
		if (iwindow == undefined) {
			iwindow = alertFrame.contentWindow;
		}
		if (plat != 'other') {
			iwindow.alert(message);
		} else {
			wAlert(message)
		}
		iframe.parentNode.removeChild(iframe);
	} catch (exc) {
		return wAlert(message);
	}
}

function getDeg(matrix) {
	var str = matrix.replace('matrix(', '');
	str = str.replace(')', '');
	var arr = str.split(',');
	var aa = Math.round(180 * Math.asin(arr[0]) / Math.PI);
	var bb = Math.round(180 * Math.acos(arr[1]) / Math.PI);
	var cc = Math.round(180 * Math.asin(arr[2]) / Math.PI);
	var dd = Math.round(180 * Math.acos(arr[3]) / Math.PI);
	var deg = 0;
	if (aa == bb || -aa == bb) {
		deg = dd;
	} else if (-aa + bb == 180) {
		deg = 180 + cc;
	} else if (aa + bb == 180) {
		deg = 360 - cc || 360 - dd;
	}
	return deg >= 360 ? 0 : deg;
	//return (aa+','+bb+','+cc+','+dd);
}

var isPlay = true;
var fatherDeg = 0;
var curBgm = 'bgm';
$("#music-icon").click(function () {
	var $children = $(this).children('i');
	if (isPlay) {
		isPlay = false;
		var childrenDeg = getDeg($children.css('transform'));
		fatherDeg = (fatherDeg + childrenDeg) % 360;
		$(this).css('transform', 'rotate(' + fatherDeg + 'deg)');
		$children.removeClass('rotateN');
		// $("#" + curBgm)[0].pause();

		$('audio').each(function (params) {
			$(this)[0].pause();
		})
	} else {
		isPlay = true;
		$children.addClass('rotateN');
		$("#" + curBgm)[0].play();
	}
});

var maskOpen = false;
$(".close").click(function () {
	if ($(this).hasClass('deep')) {

	} else {
		maskOpen = false;
	}
	$(this).parents('.mask').hide();
});

$(".show-mask").click(function () {
	maskOpen = true;
	var maskid = $(this).data('mask');
	$("#mask-" + maskid).show();
});

var anyshareclose = true;
$("#mask-share").click(function () {
	if (anyshareclose) {
		$(this).hide();
	}

});

window.requestAnimFrame = (function () {
	return window.requestAnimationFrame ||
		window.webkitRequestAnimationFrame ||
		window.mozRequestAnimationFrame ||
		function (callback) {
			window.setTimeout(callback, 1000 / 60);
		};
})();

function hideDom(id) {
	$("#" + id).removeClass('fadeIn').addClass('fadeOut animated');
	setTimeout(function () {
		$("#" + id).hide().removeClass('fadeOut');
	}, 1100);

}

function showDom(id) {
	$("#" + id).removeClass('fadeOut').addClass('fadeIn').show();
}


if (window.location.href.indexOf('vconsole') >= 0 ||
	location.host.indexOf('remmli.com') >= 0 ||
	location.host.indexOf('192.168') >= 0) {

	(function () {
		/**
		 * 动态加载js文件
		 * @param  {string}   url      js文件的url地址
		 * @param  {Function} callback 加载完成后的回调函数
		 */
		var _getScript = function (url, callback) {
			var head = document.getElementsByTagName('head')[0],
				js = document.createElement('script');

			js.setAttribute('type', 'text/javascript');
			js.setAttribute('src', url);

			head.appendChild(js);

			//执行回调
			var callbackFn = function () {
				if (typeof callback === 'function') {
					callback();
				}
			};

			if (document.all) { //IE
				js.onreadystatechange = function () {
					if (js.readyState == 'loaded' || js.readyState == 'complete') {
						callbackFn();
					}
				}
			} else {
				js.onload = function () {
					callbackFn();
				}
			}
		}

		//如果使用的是zepto，就添加扩展函数
		if (Zepto) {
			$.getScript = _getScript;
		}

	})();

	$.getScript('https://unpkg.com/vconsole@latest/dist/vconsole.min.js', function () {
		var vConsole = new VConsole();
	})
}

var winH = window.innerHeight;
var winW = window.innerWidth;
console.log(winW / winH);
var bili = winW / winH;
if (winW >= winH) {
	bili = winH / winW;
}
if (bili >= 640 / 980) {
	//ip5-
	$("body").addClass('ip5');
}
else if (bili >= 640 / 1050) {
	//ip6-
	$("body").addClass('ip6');
}
else {
	//ipx
	$("body").addClass('ipx');
}