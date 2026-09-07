
document.addEventListener("DOMContentLoaded", function () {
  var isDev = location.host.indexOf('localhost') >= 0;
  (function () {

    if (!isDev) {

      //百度埋点
      var _hmt = _hmt || [];
      (function () {
        var hm = document.createElement("script");
        hm.src = "https://hm.baidu.com/hm.js?daea4e81a39c06b557eb049b4e368fe7";
        var s = document.getElementsByTagName("script")[0];
        s.parentNode.insertBefore(hm, s);
      })();

    }
    //gio埋点
    // !(function (e, n, t, c, i) {
    //   (e[i] =
    //     e[i] ||
    //     function () {
    //       (e[i].q = e[i].q || []).push(arguments);
    //     }),
    //     (t = n.createElement('script'));
    //   let s = n.getElementsByTagName('script')[0];
    //   (t.async = 1), (t.src = c), s.parentNode.insertBefore(t, s);
    // })(window, document, 'script', 'https://assets.giocdn.com/sdk/webjs/cdp/gdp-full.js', 'gdp');
    // gdp('init', '94b19b09d2877f5a', 'abf14fbab95812ce', 'wx48fcd3afdf246f81', {
    //   host: 'collector-prod.lbxcn.com',
    //   version: '1.0'
    // });
  })();

  (typeof (wxInit) != "undefined") && wxInit();
  return;
  var plat = 'other';
  var u = navigator.userAgent;
  if (u.toLowerCase().match(/MicroMessenger/i) == 'micromessenger') {
    plat = 'weixin';
  }
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

  window.setShare = function () {
    if (!window.shareData) {
      window.shareData = {};
    }
    if (!shareData.title) {
      shareData.title = document.title;
    }
    if (!shareData.timeline) {
      shareData.timeline = shareData.title;
    }
    if (!shareData.link) {
      shareData.link = window.location.href;
    }

    if (!shareData.timelinelink) {
      shareData.timelinelink = shareData.link;
    }
    if (!shareData.desc) {
      shareData.desc = shareData.title;
    }
    if (!shareData.imgUrl) {
      shareData.imgUrl = 'https://muyang.hn.cn/img/logo.jpg';
    }
    if (!shareData.wasShare) {
      shareData.wasShare = function () { };
    }
    console.log('shareData', shareData);

    //发送好友
    // wx.onMenuShareAppMessage({
    //   title: shareData.title, // 分享标题
    //   desc: shareData.desc, // 分享描述
    //   link: shareData.link, // 分享链接
    //   imgUrl: shareData.imgUrl, // 分享图标
    //   type: 'link', // 分享类型,music、video或link，不填默认为link
    //   success: function () {
    //     shareData.wasShare && shareData.wasShare();
    //   },
    //   cancel: function () {
    //     // 用户取消分享后执行的回调函数
    //   }
    // });
    // //分享到朋友圈(旧版)
    // wx.onMenuShareTimeline({
    //   title: shareData.timeline || shareData.title,
    //   link: shareData.timelinelink || shareData.link, // 分享链接
    //   imgUrl: shareData.imgUrl, // 分享图标
    //   success: function () {
    //     shareData.wasShare && shareData.wasShare();
    //   },
    //   cancel: function () {
    //     // 用户取消分享后执行的回调函数
    //   }
    // });

    wx.updateAppMessageShareData({
      title: shareData.title, // 分享标题
      desc: shareData.desc, // 分享描述
      link: encodeURI(shareData.link), // 分享链接
      imgUrl: shareData.imgUrl, // 分享图标
      success: function () {

      },
      trigger: function () {
        console.log('分享到好友');
        shareData.wasShare && shareData.wasShare();
      }
    })
    wx.updateTimelineShareData({
      title: shareData.timeline,
      link: encodeURI(shareData.timelinelink), // 分享链接
      imgUrl: shareData.imgUrl, // 分享图标
      success: function () {

      },
      trigger: function () {
        console.log('分享到朋友圈');
        shareData.wasShare && shareData.wasShare();
      }
    })
  }

  // window.onload = function () {
  console.log('window load');
  if (!isDev && plat == 'weixin') {
  // if (1) {
    var apiUrl = 'https://muyang.hn.cn/wechat/jssdk';
    // if (location.host.indexOf('lbxcn.com') >= 0) {
    //   apiUrl = 'https://yx.lbxcn.com/out/2207lbx21/jssdk'
    // }
    // if (location.host.indexOf('localhost') >= 0) {
    //   apiUrl = 'http://localhost:3007/out/2207lbx21/jssdk'
    // }

    ajaxPost(apiUrl, {
      url: encodeURIComponent(location.href.split('#')[0])
    }, function (res) {
      var data = JSON.parse(res);
      // console.log(data);
      wx.config({
        debug: localStorage.debug || false, // 开启调试模式,调用的所有api的返回值会在客户端alert出来，若要查看传入的参数，可以在pc端打开，参数信息会通过log打出，仅在pc端时才会打印。
        appId: data.appId, // 必填，公众号的唯一标识
        timestamp: data.timestamp, // 必填，生成签名的时间戳
        nonceStr: data.nonceStr, // 必填，生成签名的随机串
        signature: data.signature, // 必填，签名，见附录1
        jsApiList: [
          'checkJsApi',
          'onMenuShareTimeline',
          'onMenuShareAppMessage',
          'updateAppMessageShareData',
          'updateTimelineShareData',
          'hideMenuItems',
          'startRecord',
          'stopRecord',
          'onVoiceRecordEnd',
          'playVoice',
          'pauseVoice',
          'stopVoice',
          'onVoicePlayEnd',
          'uploadVoice',
          'downloadVoice',
          'translateVoice',
          'getLocation',
          'openLocation',
          'previewImage'
        ],
        openTagList: ['wx-open-launch-app', 'wx-open-launch-weapp', 'wx-open-subscribe']
      });
      wx.ready(function () {
        wx.hideMenuItems({
          menuList: [
            "menuItem:share:qq",
            "menuItem:originPage",
            "menuItem:copyUrl",
            "menuItem:openWithSafari",
            "menuItem:share:email",
            "menuItem:originPage",
            "menuItem:openWithQQBrowser",
            "menuItem:share:QZone"
          ] // 要隐藏的菜单项，只能隐藏“传播类”和“保护类”按钮，所有menu项见附录3
        });

        (typeof (wxInit) != "undefined") && wxInit();
        if (window.notShare) {

        } else {
          setShare();
        }

      });

    });

  } else {
    (typeof (wxInit) != "undefined") && wxInit();
  }
  // };




});