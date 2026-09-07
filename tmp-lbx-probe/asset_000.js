(function () {

	// 获取用户信息
	function setCookie(name, value) {
		var Days = 365;
		var exp = new Date();
		exp.setTime(exp.getTime() + Days * 24 * 60 * 60 * 1000);
		document.cookie = name + "=" + escape(value) + ";expires=" + exp.toGMTString() + ';path=/';
		// 作用域全域名,单页则删除  + ';path=/'
		return value;
	}

	function getCookie(name) {
		var arr, reg = new RegExp("(^| )" + name + "=([^;]*)(;|$)");
		if (arr = document.cookie.match(reg)) {
			if (document.cookie.indexOf('koaversion') >= 0) {
				return arr[2];
			} else {
				return unescape(arr[2]);
			}
		} else {
			return '';
		}
	}

	window.setCookie = setCookie;
	window.getCookie = getCookie;

	//将url中的参数转换成json格式
	function urlToJson() { //默认参数为当前链接
		var url = arguments[0] || window.location.href;
		var arr = url.split('?');
		if (url.indexOf('?') > 0 && arr[1]) {
			var paraString = url.substring(url.indexOf('?') + 1, url.length);
			var paraJsonString;
			paraJsonString = paraString.replace(/\=/g, "\"\:\"");
			paraJsonString = paraJsonString.replace(/\&/g, "\",\"");
			paraJsonString = paraJsonString.replace(/\+/g, " ");
			paraJsonString = paraJsonString.replace(/\%26/g, "&");
			paraJsonString = paraJsonString.replace(/\%2F/g, "\/");
			paraJsonString = paraJsonString.replace(/\%0A/g, "\:");
			paraJsonString = '{"' + paraJsonString + '"}';
			return JSON.parse(paraJsonString);
		} else {
			return false; //不存在参数返回false
		}
	}
	window.urlData = urlToJson();
	window.userData = new Object();
	if (getCookie('userUnionID') || localStorage.unionid) {
		//有授权
		userData.unionid = getCookie('userUnionID') || localStorage.unionid;
		userData.openID = getCookie('userOpenID') || localStorage.openID;
		// userData.nickName = getCookie('nickName');
		// userData.nickName = decodeURIComponent(userData.nickName)
		// userData.headimgurl = getCookie('avatar');

		localStorage.unionid = userData.unionid;
		localStorage.openID = userData.openID;
		userData.nickName = localStorage.nickName || '';
		userData.headimgurl = localStorage.headimgurl || '';
	}

	var pageUrl = window.location.href;
	pageUrl = pageUrl.split('?')[0]; //去掉参数
	if (pageUrl.indexOf('127.0.0.1') >= 0 ||
		pageUrl.indexOf('192.168') >= 0 ||
		pageUrl.indexOf('localhost') >= 0) {

		//陈祥
		userData.openID = 'ocbhX6564nh6IUKEK9DJjB3bPae0';
		userData.unionid = 'oNzqMxEnsHj9xUi5ydZb25HBMPus';
		// userData.unionid = 'oNzqMxPq8Nvb4Hr9nQK-ACScyjxk';

		//别人的小程序
		// userData.openID = '82438538';
		// userData.unionid = "oNzqMxDLmqVRK9wYRwSL6N7OQX8g";

		//海绵宝宝
		// userData.openID = '9000000071433763';
		// userData.unionid = 'oNzqMxA-C97QdrX4r1SBhXMrHhkw';


		// userData.nickName = '';
		// userData.headimgurl = 'https://thirdwx.qlogo.cn/mmopen/vi_32/Q0j4TwGTfTLW0XP4gy9JgUWnnkeChr5J60mmFq7jo8lCjOu1sibuWzGp9t7QIuQgpp7HEh9twOJLNqvvDTuAdIQ/132';


		// userData.openID = 'ocbhX68w9OikOnk_iAxudIyBuas8';
		// userData.unionid = 'oNzqMxLg-NbIDJEOPhEBuS7DDMuA';
		// http://lbx.remmli.com/h5auth/2023springgame?gameCode=spring_221128_3&userUnionID=oNzqMxEnsHj9xUi5ydZb25HBMPus&userOpenID=ocbhX6564nh6IUKEK9DJjB3bPae0



		// userData.openID = 'ocbhX66FkAPZjvmFxhkiLfqveHag';
		// userData.unionid = 'oNzqMxIj4GhaucJB_qxWPJjCnGVw';

		// userData.openID = 'ocbhX63wzrKQOnTrSwIRCBxFgpjA';
		// userData.unionid = 'oNzqMxPq8Nvb4Hr9nQK-ACScyjxk';

		// userData.openID = 'ocbhX651IhUWFm94AtmPLrYD7CLk';
		// userData.unionid = 'noone8';

		userData.nickName = localStorage.nickName || '';
		userData.headimgurl = localStorage.headimgurl || '';



		//测试分享路径
		// http://localhost/h5auth/2023springgame?source=5&gameCode=spring_221128_3&shareUnionID=oNzqMxEnsHj9xUi5ydZb25HBMPus&shareOpenID=ocbhX6564nh6IUKEK9DJjB3bPae0&shareCardID=6
	}

})();
