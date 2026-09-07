// 压缩命令
// uglifyjs main.js -o main.min.js -m reserved=[$] -c
var __assign = (this && this.__assign) || function () {
    __assign = Object.assign || function(t) {
        for (var s, i = 1, n = arguments.length; i < n; i++) {
            s = arguments[i];
            for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p))
                t[p] = s[p];
        }
        return t;
    };
    return __assign.apply(this, arguments);
};
var gdp = function () { };
window.isDev = false;
window.apiHost = 'https://yx.lbxcn.com';
if (location.host.indexOf('127.0.0.1') >= 0
    || location.host.indexOf('localhost') >= 0
    || location.host.indexOf('remmli.com') >= 0
    || location.host.indexOf('muyang.hn.cn') >= 0) {
    isDev = true;
}
if (isDev) {
    // apiHost = 'https://muyang.hn.cn/lbx';
    // apiHost = 'http://localhost:3007';
}
if (localStorage.debug || isDev) {
    (function () {
        /**
         * 鍔ㄦ€佸姞杞絡s鏂囦欢
         * @param  {string}   url      js鏂囦欢鐨剈rl鍦板潃
         * @param  {Function} callback 鍔犺浇瀹屾垚鍚庣殑鍥炶皟鍑芥暟
         */
        var _getScript = function (url, callback) {
            var head = document.getElementsByTagName('head')[0], js = document.createElement('script');
            js.setAttribute('type', 'text/javascript');
            js.setAttribute('src', url);
            head.appendChild(js);
            //鎵ц鍥炶皟
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
                };
            }
            else {
                js.onload = function () {
                    callbackFn();
                };
            }
        };
        //濡傛灉浣跨敤鐨勬槸zepto锛屽氨娣诲姞鎵╁睍鍑芥暟
        if (Zepto) {
            $.getScript = _getScript;
        }
    })();
    $.getScript('https://unpkg.com/vconsole@latest/dist/vconsole.min.js', function () {
        var vConsole = new VConsole();
    });
}
var m_h5 = (function () {
    var winH = window.innerHeight;
    var whb = window.innerWidth / window.innerHeight;
    if (whb <= 640 / 1200) {
        //ipx
        $("body").addClass('ipx');
    }
    else {
        //ip6-
        $("body").addClass('ip6');
    }
    $('.main').attr('view-height', Math.ceil(750 / whb));
    window.virtualH = winH / (winH / 1465);
    // anyshareclose = false;
    //确认页面基本参数
    if (urlData && urlData.source) {
        // console.log(urlData.source);
        window.source = urlData.source;
    }
    else {
        window.source = localStorage.source || '5';
    }
    localStorage.source = window.source;
    window.gameCode = getCookie('gameCode') || 'spring_221128_3';
    if (urlData && urlData.gameCode) {
        // console.log(urlData.gameCode);
        gameCode = urlData.gameCode;
    }
    $(document).on('ajaxBeforeSend', function (e, xhr, options) {
        if (options.type == "GET" && options.url.indexOf('?') >= 0) {
            options.url += '&rts=' + new Date().valueOf();
        }
    });
})();
var hot_fix = (function () {
    // 热修复逻辑
    $('#mask-share img').attr('src', 'https://muyang.hn.cn/hdh5/2026/01lbxnhj/img/u3.png');
})();
function wxInit() {
    $('#page-loading').show();
    console.log(location.href);
    // gdp('track', 'spring2023_game_loading', {
    //     game_source: localStorage.source,
    // });
    $('.has-wx-btn').removeClass('has-wx-btn');
    var initPage = function () {
        // return;
        m_bgm.init();
        // gdp('track', 'spring2023_game_main', {
        //     game_source: localStorage.source,
        // });
        $('#page-start').show();
        $('#page-loading').addClass('fadeOut');
        setTimeout(function () {
            $('#page-start .content').show();
            m_game.init();
            // m_prize.getZoumadeng();
            setTimeout(function () {
                $('#page-game').show();
                m_jump.init();
            }, 500);
        }, 800);
    };
    if (document.referrer && document.referrer.indexOf('lbxdrugs.com') >= 0) {
        //是会员授权过来的
        console.log('document.referrer', document.referrer);
        initPage();
    }
    else {
        m_loading.over(function () {
            initPage();
        }, urlData.dev ? 'real' : 'fake');
    }
    if (location.href.indexOf('dev') >= 0) {
        // $.post(apiHost + "/api/client/spring2026/game/getcard", {
        //     gameCode: gameCode,
        //     unionID: 'oNzqMxCsCYUWzAEC6hY7PPrPw65k',
        //     cardID: 9
        // }, function (res) {
        //     console.log('获得菜品卡', res.data);
        // });
    }
}
var m_bgm = (function () {
    var attr = {
        hasSound: false,
        allowSound: false
    };
    function play() {
        document.getElementById('bgm').play();
        attr.hasSound = true;
    }
    function pause() {
        $('#sounds-icon').addClass('pause').removeClass('play');
        document.getElementById('bgm').pause();
        attr.hasSound = false;
    }
    $('#sounds-icon').click(function name() {
        attr.hasSound = $('#sounds-icon').hasClass('play');
        if (attr.hasSound) {
            attr.allowSound = false;
            pause();
        }
        else {
            attr.allowSound = true;
            play();
        }
        console.log(attr.allowSound);
    });
    return {
        pause: pause,
        play: play,
        init: function () {
            document.getElementById('bgm').onplay = function (e) {
                // console.log('onplay', e)
                $('#sounds-icon').addClass('play').removeClass('pause');
            };
            // console.log(plat);
            $('#sounds-icon').show().addClass('pause');
            // if (plat == 'weixin') {
            // play(); //微信无法再自动播放了      
            // attr.allowSound = true;
            // wx.miniProgram && wx.miniProgram.getEnv && wx.miniProgram.getEnv(function (res) {
            // console.log('getEnv',res);
            if (u.indexOf('miniProgram') >= 0) {
                plat = 'wxapp';
                $('#mask-share').addClass('wxapp');
                document.addEventListener("visibilitychange", function () {
                    console.log('小程序模式切换可见', document.hidden);
                    if (document.hidden) {
                        if (attr.hasSound) {
                            console.log('页面被挂起,暂停播放');
                            pause();
                        }
                    }
                    else {
                        m_task.showTask(false);
                        if (attr.allowSound) {
                            play();
                        }
                    }
                });
            }
            else {
                //是H5模式
                document.addEventListener("visibilitychange", function () {
                    //已经点击了小程序按钮
                    if (document.hidden) {
                        if (attr.hasSound) {
                            pause();
                        }
                    }
                    else {
                        m_task.comeBackH5();
                        if (attr.allowSound) {
                            play();
                        }
                    }
                });
            }
            m_task.initWxappViewBtn();
            // });
            // } else {
            //     $('#sounds-icon').addClass('pause').removeClass('play');
            // }
        },
        attr: attr,
    };
})();
var m_loading = (function () {
    var $loadingtext = $('#loading-text');
    var $loadingbar = $('.loading-bar .inner');
    var imgs = [
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/a0.jpg",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/a1.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/b0.jpg",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/b1.jpg",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/b21.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/b31.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/b32.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/b33.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/b41.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/b42.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/btn-avatar.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/btn-prize.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/btn-rank.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/btn-start.jpg",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/c3.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/d1.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/d21.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/d22.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/d31.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/d32.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/d33.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/d41.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/d42.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/e21.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/e22.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/e23.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/e24.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/e32.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/goods.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/ico_xuanzhong.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/inp-name.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/k31.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/l21.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/l22.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/loading.gif",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/loading.jpg",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/o11.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/o12.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/o13.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/o14.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/o15.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/o16.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/p-t.png",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/prize-img.jpg",
        "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/prize-img2.jpg",
    ];
    var wasLoading = 0;
    var d = 1;
    var dotTimer = setInterval(function () {
        d++;
        if (d > 3) {
            d = 1;
        }
        var dot = '';
        for (var i = 0; i < d; i++) {
            dot += '.';
        }
        // $loadingtext.text('游戏加载中，马上进入' + dot);
    }, 600);
    return {
        over: function (callback, type) {
            if (type === void 0) { type = 'fake'; }
            preloadImages(imgs, function (num) {
                // console.log('加载完成图片数：', num);
                var percent = parseInt(num / imgs.length * 100);
                if (type == 'fake') {
                    //模拟假的
                    wasLoading = percent;
                }
                else {
                    //真的
                    $loadingbar.css('width', percent + '%');
                }
            }, function () {
                var imgHtml = '';
                for (var i = 0; i < imgs.length; i++) {
                    var url = imgs[i];
                    imgHtml += "<img src=\"".concat(url, "\" />");
                }
                $('#page-loading .hide-img').html(imgHtml);
                if (type == 'fake') {
                    //模拟假的
                    wasLoading = 100;
                }
                else {
                    //真的
                    setTimeout(function () {
                        callback && callback();
                        clearInterval(dotTimer);
                    }, 1000);
                }
            });
            if (type == 'fake') {
                //模拟假的
                var curLoading_1 = 0;
                var timer_1 = setInterval(function () {
                    curLoading_1 += randomNum(13, 27);
                    // console.log(curLoading, wasLoading)
                    if (curLoading_1 > wasLoading) {
                        $loadingbar.css('width', wasLoading + '%');
                    }
                    else {
                        $loadingbar.css('width', curLoading_1 + '%');
                    }
                    if (curLoading_1 >= 100) {
                        clearInterval(timer_1);
                        setTimeout(function () {
                            clearInterval(dotTimer);
                            callback && callback();
                        }, 500);
                    }
                }, 500);
            }
        }
    };
})();
var m_jump = (function () {
    var util = {
        init: function () {
            var a = "ontouchstart" in window;
            this.mousedown = a ? "touchstart" : "mousedown", this.mousemove = a ? "touchmove" : "mousemove", this.mouseup = a ? "touchend" : "mouseup";
        },
        resize: function () {
            var a = 640, b = 960, c = document.body.clientWidth, d = document.body.clientHeight, e = Math.min(c / a, d / b);
            Game.scale = e, $("#cvs").show();
        }, img: {
            imgCache: {}, get: function (a) {
                return this.imgCache[a] ? this.imgCache[a] : this.imgCache;
            }, load: function (a, b) {
                var c = this;
                if (c.imgCache[a.key])
                    return b && b(), void (b = null);
                var d = new Image;
                d.onload = function () { c.imgCache[a.key] = this, b && b(), b = null; }, d.src = a.src;
            }, loadAll: function (a, b) {
                this.imgNum = 0,
                    this.loadOver(a, b);
            }, loadOver: function (a, b) {
                var c = this;
                this.load(a[c.imgNum], function () { c.imgNum++, a[c.imgNum] ? c.loadOver(a, b) : (b && b(), b = null); });
            }
        }
    };
    var moveBg = 0;
    var $bg = $('#page-game .bg');
    var $score = $('#page-game .score span');
    var BGH = parseInt($bg.css('height').replace('px', '')) - virtualH;
    // $('.bg .start').css('bottom', -0.5 * (1500 - virtualH) + 'px');
    var moveStep = BGH / 50;
    var cloudW = 127;
    var cloudH = 127;
    var rabbitW = 127;
    var rabbitH = 115; // 79
    var jumpSounds = document.getElementById('jump-sounds');
    var failSounds = document.getElementById('fail-sounds');
    var cloudParams = {
        width: cloudW, height: cloudH, img: "cloud", dir: "right",
    };
    var baseCloud = [
        __assign(__assign({}, cloudParams), { margin: 640 - (406 + cloudW), type: "left", left: 256, top: 60, dir: "left", speed: 2 }),
        __assign(__assign({ margin: 256, type: "right", left: 406, top: 60 }, cloudParams), { img: "manghe", hasPrize: true, dir: "left", speed: 2 }),
        __assign(__assign({ margin: 640 - (406 + cloudW), type: "left", left: 256, top: 300 }, cloudParams), { speed: 2 }),
        __assign(__assign({ margin: 256, type: "right", left: 406, top: 300 }, cloudParams), { speed: 2 }),
        __assign(__assign({ left: 256, top: 540 }, cloudParams), { speed: 2 }),
    ];
    var baseRabbit = {
        left: 256, top: 754, width: rabbitW, height: rabbitH, img: "rabbit", dir: "right", speed: 4
    };
    var Game = {
        canvas: null, cvs: null, scale: 1, score: 0, hasPrize: null, isStart: true, isGame: false, isOver: false, isPlaySound: false,
        onlyCoins: false, isStop: false,
        bg: { speed: 1, top1: 0 },
        cloudData: JSON.parse(JSON.stringify(baseCloud)),
        cloudMove: false,
        rabbit: __assign({}, baseRabbit),
        jumpRabbit: {
            left: 250, top: 684, width: rabbitW, height: rabbitH, img: "jump_rabbit", dir: "right", speed: 4
            // left: 290, top: 684, width: 132, height: 197, img: "jump_rabbit", dir: "right", speed: 4
        },
        addScore: {
            left: 200, top: 780, width: 50, height: 40, img: "score_1", dir: "right", speed: 4
        }
    };
    var startTime = 0;
    var endTime = 0;
    function gameStart() {
        Game.canvas = $("#cvs");
        Game.cvs = Game.canvas[0].getContext("2d");
        drawStart();
        initEvent();
    }
    function drawStart() {
    }
    function gameing() {
        runGame();
    }
    var runGameTimer = null;
    function runGame() {
        // console.log('runGame');
        if (Game.isStop) {
            Game.cloudMove = false;
            Game.isGame = false;
            Game.isOver = true;
            setTimeout(gameOver, 400);
            return;
        }
        update();
        draw();
        runGameTimer = setTimeout(runGame, 1000 / 60);
        // window.requestAnimationFrame && window.requestAnimationFrame(runGame)
    }
    function gameOver() {
        console.log('gameOver');
        m_bgm.attr.allowSound && failSounds.play();
        $('#mask-game-continue').show();
        clearTimeout(runGameTimer);
    }
    function initEvent() {
        $('.btn-go').click(function () {
            var gameInfo = window.gameInfo;
            var startDate = gameInfo.startDate;
            var endtDate = gameInfo.endtDate;
            if (startDate && new Date().valueOf() < new Date(startDate).valueOf()) {
                return alert('活动未开始');
            }
            if (endtDate && new Date().valueOf() > new Date(endtDate).valueOf()) {
                return alert('活动已结束');
            }
            if ($('#page-loading').length > 0) {
                $('#page-loading').remove();
            }
            $('#mask-package').hide();
            m_game.checkChance(function () {
                m_bgm.play();
                if (Game.isStart) {
                    $('#mask-package .btn-back').text('返回游戏');
                    $('#page-start').addClass('fadeOut');
                    // $('#page-start').hide();
                    startTime = new Date().valueOf();
                    Game.isStart = false;
                    Game.isGame = true;
                    gameing();
                }
            });
        });
        $('#mask-game-continue .btn-use').click(function () {
            //消耗金币继续
            if (Game.isOver) {
                m_game.useCoins(function () {
                    $('#mask-game-continue').hide();
                    Game.cloudMove = true;
                    Game.isGame = true;
                    Game.isOver = false;
                    Game.isStop = false;
                    var d = Game.cloudData[0];
                    d.img = 'cloud';
                    d.hasPrize = false;
                    Game.rabbit.dir = d.dir;
                    Game.rabbit.speed = d.speed;
                    Game.rabbit.left = d.left;
                    Game.rabbit.type = d.type;
                    Game.rabbit.initPath = d.initPath;
                    Game.rabbit.margin = d.margin;
                    update();
                    draw();
                    runGameTimer = setTimeout(runGame, 1000 / 60);
                });
            }
        });
        var endCount = function () {
            endTime = new Date().valueOf();
            m_points.savePoints(Game.score, Math.floor((endTime - startTime) / 1000));
            $('#mask-package .btn-back').text('返回首页');
            $('#mask-game-over .score').text(Game.score);
            var endData = m_game.endRound();
            console.log(endData);
            if (endData.prize) {
                $('#mask-game-over .prize span').text('1');
            }
            else {
                $('#mask-game-over .prize span').text('0');
            }
            if (endData.card) {
                $('#mask-game-over .card span').text('1');
            }
            else {
                $('#mask-game-over .card span').text('0');
            }
            $('#mask-game-over .coins span').text(endData.coins);
            $('#mask-game-over').show();
            resetGame();
        };
        $('#mask-game-continue .btn-skip').click(function () {
            console.log('结束本轮游戏', Game.isOver);
            if (Game.isOver) {
                $('#mask-game-continue').hide();
                $('#mask-game-over .score-div').html("<div class=\"score-div\">\u6311\u6218\u5B8C\u6210\u5C42\u6570\uFF1A<span class=\"score\"></span>\u5C42</div>");
                endCount();
            }
        });
        $('#mask-game-over .btn').click(function () {
            $('#page-start').removeClass('fadeOut').addClass('fadeIn');
            // $('#page-start').show();
            setTimeout(function () {
                $score.text('0');
                moveBg = 0;
                $bg.css('transition', "none");
                $bg.css('transform', "translateY(".concat(moveBg, "px)"));
            }, 800);
            setTimeout(function () {
                $bg.css('transition', "all .5s");
            }, 1000);
        });
        var lastJump = false;
        $('.btn-jump').click(function () {
            console.log(Game.score);
            if (Game.score >= 100) {
                //最多100层
                Game.isOver = true;
                $('#mask-game-over .score-div').html("<div class=\"score-div\">\u6311\u6218\u6210\u529F\uFF1A<span class=\"score\"></span>\u5C42</div>");
                return endCount();
            }
            if (lastJump) {
                return;
            }
            lastJump = true;
            setTimeout(function () {
                lastJump = false;
            }, 300);
            m_bgm.attr.allowSound && jumpSounds.play();
            if (Game.isGame) {
                moveBg += moveStep;
                $bg.css('transform', "translateY(".concat(moveBg, "px)"));
                // Game.cvs.clearRect(0, 0, 640, 960);
                if (Game.rabbit.istiao) {
                    return true;
                }
                Game.rabbit.istiao = true;
                Game.jumpTime = Date.now();
                Game.EndTop = Game.bg.top1 + 240;
                return true;
            }
        });
    }
    function resetGame() {
        Game.cvs.clearRect(0, 0, 640, 960);
        Game.isStart = true;
        Game.cloudMove = false;
        Game.isGame = true;
        Game.isOver = false;
        Game.isStop = false;
        Game.score = 0;
        Game.cloudData = JSON.parse(JSON.stringify(baseCloud));
        Game.rabbit = __assign({}, baseRabbit);
        Game.bg = {
            speed: 1, top1: 0
        };
    }
    function update() {
        if (Game.rabbit.istiao) {
            Game.bg.top1 += 16;
            if (Game.bg.top1 >= Game.EndTop) {
                Game.bg.top1 = Game.EndTop;
                Game.rabbit.istiao = false;
                Game.cloudMove = true;
                var a = -Game.bg.top1 + 60;
                var c = Math.floor(Math.random() * 200);
                var cengshu = Game.EndTop / 240;
                var level = m_game.getDiffculty(cengshu);
                var hasPrize = Math.random() < 0.3;
                var b = Math.random() < 0.5;
                //确认难度
                switch (level) {
                    case 0:
                        Game.cloudData.push(__assign(__assign({}, cloudParams), { margin: 640 - (406 + cloudW), type: "left", left: 256, top: a, hasPrize: hasPrize && b, img: hasPrize && b ? "manghe" : "cloud", speed: 3 }));
                        Game.cloudData.push(__assign(__assign({}, cloudParams), { margin: 256, type: "right", left: 406, top: a, hasPrize: hasPrize && !b, img: hasPrize && !b ? "manghe" : "cloud", speed: 3 }));
                        break;
                    case 1:
                        Game.cloudData.push(__assign(__assign({}, cloudParams), { margin: 640 - (c + 190 + 127), type: "left", left: c, top: a, hasPrize: hasPrize && b, img: hasPrize && b ? "manghe" : "cloud", speed: 4 }));
                        Game.cloudData.push(__assign(__assign({}, cloudParams), { margin: c, type: "right", left: c + 190, top: a, hasPrize: hasPrize && !b, img: hasPrize && !b ? "manghe" : "cloud", speed: 4 }));
                        break;
                    case 2:
                        Game.cloudData.push(__assign(__assign({}, cloudParams), { margin: 640 - (c + 190 + 127), type: "left", left: c, top: a, hasPrize: false, speed: 5 }));
                        Game.cloudData.push(__assign(__assign({}, cloudParams), { margin: c, type: "right", left: c + 190, top: a, hasPrize: hasPrize && b, img: hasPrize && b ? "manghe" : "cloud", speed: 5 }));
                        break;
                    case 3:
                        Game.cloudData.push(__assign(__assign({}, cloudParams), { margin: 640 - (c + 190 + 127), type: "left", left: c + 127, top: a, hasPrize: hasPrize, img: hasPrize ? "manghe" : "cloud", speed: 5 }));
                        break;
                    case 4:
                        Game.cloudData.push(__assign(__assign({}, cloudParams), { margin: 640 - (c + 190 + 127), type: "left", left: c + 127, top: a, hasPrize: hasPrize && b, img: hasPrize && b ? "manghe" : "cloud", speed: 6 }));
                        break;
                    default:
                        Game.cloudData.push(__assign(__assign({}, cloudParams), { margin: 640 - (c + 190 + 127), type: "left", left: c + 127, top: a, hasPrize: hasPrize && b, img: hasPrize && b ? "manghe" : "cloud", speed: 6 }));
                        break;
                }
                checkDiaoLuo(function (d) {
                    Game.yaotiaoTime = Date.now();
                    Game.rabbit.dir = d.dir;
                    Game.rabbit.speed = d.speed;
                    Game.rabbit.left = d.left;
                    Game.rabbit.type = d.type;
                    Game.rabbit.initPath = d.initPath;
                    Game.rabbit.margin = d.margin;
                    if (d.hasPrize) {
                        //d是云
                        d.img = 'cloud';
                        console.log('跳中盲盒了');
                        Game.hasPrize = d.hasPrize;
                        Game.score += 1;
                        m_game.getRoundPrize(function () {
                        }, function (coins) {
                        });
                    }
                    else {
                        Game.score += 1;
                        Game.hasPrize = false;
                    }
                    $score.text(Game.score);
                }, function () {
                    Game.isStop = true;
                });
            }
        }
    }
    function checkDiaoLuo(d, a) {
        for (var b = 0; b < Game.cloudData.length; b++) {
            var c = Game.cloudData[b];
            if (Math.abs((Game.rabbit.left) - (c.left)) <= 80) {
                if (Math.abs((Game.rabbit.top) - (c.top + Game.bg.top1)) <= 80) {
                    if (d) {
                        d(c);
                    }
                    return true;
                }
            }
        }
        if (a) {
            a();
        }
    }
    function draw() {
        Game.cvs.clearRect(0, 0, 640, 960);
        for (var b = 0; b < Game.cloudData.length; b++) {
            var e = Game.cloudData[b];
            if (Game.cloudMove) {
                if (e.initPath == undefined) {
                    e.initPath = e.left;
                }
                if (e.dir == "right") {
                    e.left += e.speed;
                    if (e.type == "right" || e.type == undefined) {
                        if (e.left >= 513) {
                            // e.left = 513;
                            e.dir = "left";
                        }
                    }
                    else {
                        if (e.type == "left") {
                            if (e.left >= (e.initPath + e.margin)) {
                                // e.left = e.initPath + e.margin; 
                                e.dir = "left";
                            }
                        }
                    }
                }
                else {
                    if (e.dir == "left") {
                        e.left -= e.speed;
                        if (e.type == "left" || e.type == undefined) {
                            if (e.left <= 0) {
                                // e.left = 0;
                                e.dir = "right";
                            }
                        }
                        else {
                            if (e.type == "right") {
                                if (e.left <= (e.initPath - e.margin)) {
                                    // e.left = e.initPath - e.margin;
                                    e.dir = "right";
                                }
                            }
                        }
                    }
                }
            }
            var d = e.top + Game.bg.top1;
            drawImage(e.img, e.left, d, e.width, e.height);
            if (d >= 960) {
                Game.cloudData.splice(b, 1);
            }
        }
        if (Game.isStop) {
            drawImage("jump_wrabbit", Game.rabbit.left + 0, Game.rabbit.top + 70, rabbitW, rabbitH);
            // drawImage("water", Game.rabbit.left + 0, Game.rabbit.top - 0 - 23, 115, 151);
            return;
        }
        var e = Game.rabbit;
        if (Game.cloudMove) {
            if (e.initPath == undefined) {
                e.initPath = e.left;
            }
            if (e.dir == "right") {
                e.left += e.speed;
                if (e.type == "right" || e.type == undefined) {
                    if (e.left >= 513) {
                        // e.left = 513;
                        e.dir = "left";
                    }
                }
                else {
                    if (e.type == "left") {
                        if (e.left >= (e.initPath + e.margin)) {
                            // e.left = e.initPath + e.margin; 
                            e.dir = "left";
                        }
                    }
                }
            }
            else {
                if (e.dir == "left") {
                    e.left -= e.speed;
                    if (e.type == "left" || e.type == undefined) {
                        if (e.left <= 0) {
                            // e.left = 0;
                            e.dir = "right";
                        }
                    }
                    else {
                        if (e.type == "right") {
                            if (e.left <= (e.initPath - e.margin)) {
                                // e.left = e.initPath - e.margin;
                                e.dir = "right";
                            }
                        }
                    }
                }
            }
        }
        var d = e.top + 6;
        var g = Game.jumpRabbit;
        var a = Game.rabbit.istiao;
        var f = Date.now();
        if ((f - Game.jumpTime) <= 500 && a) {
            drawImage(g.img, e.left, d, g.width, g.height);
            return;
        }
        drawImage(e.img, e.left, d, e.width, e.height);
        var c = Date.now();
        if ((c - Game.yaotiaoTime) <= 500) {
            addScore();
        }
    }
    function addScore() {
        var c = Game.rabbit;
        var a = c.top;
        if (Game.score == 0) {
            return;
        }
        else {
            if (Game.score > 0 && Game.hasPrize && Game.onlyCoins) {
                var b = Game.addScore;
                // drawImage("score_3", c.left + 50, a - 50, b.width, b.height);
            }
            else {
                var b = Game.addScore;
                // drawImage("score_1", c.left + 50, a - 50, b.width, b.height);
            }
        }
    }
    function drawImage(b, e, d, c, a) {
        Game.cvs.drawImage(util.img.get(b), e, d, c, a);
    }
    return {
        init: function () {
            util.init();
            util.resize();
            window.onresize = function () { util.resize(); };
            var a = [
                { key: "manghe", src: "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/b33.png" },
                { key: "cloud", src: "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/b32.png" },
                { key: "rabbit", src: "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/b41.png" },
                { key: "jump_rabbit", src: "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/b42.png" },
                { key: "jump_wrabbit", src: "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/b43.png" },
            ];
            util.img.loadAll(a, function () {
                gameStart();
            });
        }
    };
})();
var yiyuanBtnUrl = '/activity/pages/myCoupon/myCoupon?type=1&utm=game';
var m_game = (function () {
    var rank_info = '';
    var prize_info = '';
    var map_brand_info = [];
    var cur_map_brand = null;
    var limitPhone = [];
    var allowUser = true;
    var startDate, endtDate, limitCity, gameStatus;
    var diffculty = [0, 5, 10, 15, 20, 25];
    var curCengshu = 0;
    var conins_config = [];
    var thisRoundPrize = {
        prize: null,
        card: null,
    };
    var thisRoundGet = {
        prize: null,
        card: null,
        coins: 0,
    };
    var goOauth = function () {
        if (location.host.indexOf('lbxcn.com') >= 0) {
            //正式版
            window.location.replace('https://open.weixin.qq.com/connect/oauth2/authorize?appid=wxd7c4ac832c697f6f&redirect_uri=https://wx.lbxdrugs.com/lbxdrugs-weoffacc/program/pages/html/result/authorization3.html?appid=wxd7c4ac832c697f6f&response_type=code&scope=snsapi_userinfo&state=STATE&connect_redirect=1&#wechat_redirect');
        }
        else {
            window.location.replace('https://open.weixin.qq.com/connect/oauth2/authorize?appid=wx48fcd3afdf246f81&redirect_uri=http://wechattest.lbxdrugs.com/lbxdrugs-weoffacc-uat/pages/html/result/authorization3.html?appid=wx48fcd3afdf246f81&response_type=code&scope=snsapi_userinfo&state=STATE&connect_redirect=1&#wechat_redirect');
        }
    };
    var updateUserInfo = function () {
        $.post(apiHost + '/api/client/spring2026/user/editinfo', {
            gameCode: gameCode,
            openID: userData.openID,
            unionID: userData.unionid,
            name: localStorage.nickName || '',
            avatar: localStorage.headimgurl || '',
            // deptId: localStorage.shop_id,
        }, function (res) {
            localStorage.game_user_info = JSON.stringify(res.data);
            window.game_user_info = res.data;
            //
            // limitPhone.length > 0 && checkPhone();
        });
    };
    var updateProvinceData = function (add) {
        if (add === void 0) { add = ''; }
        //获取省份数据
        if (localStorage.userProvince) {
            console.log('所属省份', localStorage.userProvince, getCodeValue(localStorage.userProvince));
            $.get(apiHost + '/api/client/spring2026/count/detail', {
                gameCode: gameCode,
                province: localStorage.userProvince || '',
                add: add
            }, function (res) {
                if (res.code > 0) {
                    var provinceName = getCodeValue(localStorage.userProvince);
                    if (provinceName.length > 3) {
                        //所有自治区简称
                        provinceName = provinceName.substr(0, 2);
                    }
                    $('.province .provinceName').text(provinceName);
                    var totalNum = res.data.realNumber + res.data.incrementNumber + res.data.virtualNumber;
                    $('.province .count').text(totalNum);
                }
            });
        }
        //配置虚拟兔子数
        // $.post(apiHost + '/api/client/spring2026/count/set', {
        //     gameCode,
        //     province: localStorage.userProvince || '',
        //     virtualNumber: 100,
        // }, (res) => {
        //     const totalNum = res.data.realNumber + res.data.incrementNumber + res.data.virtualNumber;
        //     console.log(totalNum)
        // })
    };
    var geolocation = null;
    var geocoder = null;
    var nearestShopID = null;
    var initGps = function (callback, getNearestShopID) {
        if (getNearestShopID === void 0) { getNearestShopID = false; }
        // callback && callback(1384);
        // return '直接取消附近门店';
        if (nearestShopID) {
            //已经获取过最近的门店了
            callback && callback(nearestShopID);
            return;
        }
        globalLoading.show();
        var getCity = function (latitude, longitude) {
            localStorage.latitude = latitude;
            localStorage.longitude = longitude;
            var checkCity = function () {
                if (limitCity) {
                    var userCity = localStorage.userCity;
                    //限制了城市
                    if (userCity) {
                        var limitCityList = limitCity.split(',');
                        var canPlay = false;
                        for (var i = 0; i < limitCityList.length; i++) {
                            var item = limitCityList[i];
                            if (item.indexOf('0000') > 0) {
                                //是省级
                                if (item.substr(0, 2) == userCity.substr(0, 2)) {
                                    canPlay = true;
                                }
                            }
                            else {
                                //是市级
                                if (item.substr(0, 4) == userCity.substr(0, 4)) {
                                    canPlay = true;
                                }
                            }
                        }
                        if (canPlay) {
                            //命中了活动城市
                            saveShopID();
                        }
                        else {
                            weui.alert('您不在活动城市，感谢您对老百姓大药房的关注！');
                            globalLoading.hide();
                        }
                    }
                    else {
                        weui.alert('获取所在城市失败，请稍后再试');
                        globalLoading.hide();
                    }
                }
                else {
                    saveShopID();
                }
            };
            var saveShopID = function () {
                if (getNearestShopID && localStorage.latitude) {
                    $.get(apiHost + '/out/2026api/getlbxStoreList', {
                        Latitude: localStorage.latitude, Longitude: localStorage.longitude
                    }, function (res) {
                        console.log(res);
                        if (res.data && res.data && res.data.rows.length > 0) {
                            m_prize.initStore(res.data.rows);
                            var dept = res.data.rows[0];
                            localStorage.shop_id = dept.deptCode;
                        }
                        else {
                            localStorage.shop_id = 1384;
                        }
                        nearestShopID = localStorage.shop_id;
                        callback && callback(nearestShopID);
                        globalLoading.hide();
                    });
                }
                else {
                    callback && callback();
                    globalLoading.hide();
                }
            };
            checkCity();
            // saveShopID();
        };
        var getLocation = function () {
            console.log('plat', plat);
            if (plat == 'other') {
                // m_points.getProvinceRank(true, (totalNum) => {
                //     $('.province .count').text(totalNum);
                // })
                // return getCity(28.15, 112.95);
            }
            var getGPSLocation = function () {
                navigator.geolocation.getCurrentPosition(function (position) {
                    var gps = transformFromWGSToGCJ(position.coords.latitude, position.coords.longitude);
                    console.log("经度: " + gps.latitude + "纬度: " + gps.longitude);
                    $.get('https://qqnews.hn.cn/ip', {}, function (res) {
                        if (res.province && res.city) {
                            localStorage.userProvince = getNameCode(res.province);
                            localStorage.userCity = getNameCode(res.city);
                        }
                        getCity(gps.latitude, gps.longitude);
                        // getCity(position.coords.latitude, position.coords.longitude);
                    });
                }, function (error) {
                    console.error("获取位置失败: " + error.message);
                    globalLoading.hide();
                    m_points.getProvinceRank(true, function (totalNum) {
                        $('.province .count').text(totalNum);
                    });
                    localStorage.shop_id = 1384;
                    nearestShopID = localStorage.shop_id;
                    callback && callback(nearestShopID);
                }, {
                    enableHighAccuracy: true,
                    timeout: 5000,
                    maximumAge: 0 // 不使用缓存位置
                });
            };
            getGPSLocation();
        };
        getLocation();
    };
    var initAvatar = function () {
        var $avatars = $('#mask-avatar .item');
        var headimgurl = localStorage.headimgurl || '';
        $('.user-info .avatar').click(function () {
            $('#mask-avatar').show();
        });
        if (userData.unionid) {
            //如果没有昵称，第一次打开则弹框
            if (!localStorage.nickName) {
                $('#mask-avatar').show();
                gdp('track', 'spring2023_game_avatar', {
                    game_source: localStorage.source,
                });
            }
            else {
                //预填信息
                $('#inp-nickName').val(localStorage.nickName);
                $('.headimgurl').attr('src', localStorage.headimgurl);
                $('.nickName').text(localStorage.nickName);
                $avatars.each(function () {
                    if ($(this).children('img').attr('src') == localStorage.headimgurl) {
                        $(this).addClass('selected');
                        return false;
                    }
                });
            }
        }
        $avatars.click(function () {
            $avatars.removeClass('selected');
            $(this).addClass('selected');
            headimgurl = $(this).children('img').attr('src');
        });
        $('#mask-avatar .btn').click(function () {
            if (!headimgurl) {
                return weui.alert('请选择头像');
            }
            if (!$('#inp-nickName').val()) {
                return weui.alert('请输入昵称');
            }
            localStorage.headimgurl = headimgurl;
            localStorage.nickName = $('#inp-nickName').val();
            $('.headimgurl').attr('src', localStorage.headimgurl);
            $('.nickName').text(localStorage.nickName);
            $('#mask-avatar').hide();
            if (userData.unionid) {
                updateUserInfo();
            }
            if (!localStorage.userProvince) {
                initGps(updateProvinceData);
            }
            if ($('#mask-pictures .myzp').length > 0) {
                $('#mask-pictures .myzp p').text(localStorage.nickName);
            }
        });
    };
    var coinsTipsTimer = null;
    return {
        init: function () {
            initAvatar();
            if (localStorage.userProvince) {
                updateProvinceData();
            }
            else {
                //没有定位数据
                m_points.getProvinceRank(true, function (totalNum) {
                    $('.province .count').text(totalNum);
                });
            }
            if (!userData.unionid) {
                //未登录
                $('#page-start .btn-go .num').hide();
                $('#page-start .btn-go .text').css('line-height', '67px');
            }
            //获取游戏基本配置
            $.get(apiHost + '/api/client/spring2026/game/config', {
                gameCode: gameCode,
            }, function (res) {
                console.log(res);
                if (res.code == 0) {
                    gameStatus = 0;
                    weui.alert('活动未开放');
                    return;
                }
                var _a = res.data, materialList = _a.materialList, taskList = _a.taskList, gameInfo = _a.gameInfo;
                if (gameInfo) {
                    window.gameInfo = gameInfo;
                    startDate = gameInfo.startDate;
                    endtDate = gameInfo.endtDate;
                    limitCity = gameInfo.city;
                    gameStatus = gameInfo.status;
                    document.title = gameInfo.name;
                }
                if (materialList && taskList) {
                    for (var _i = 0, materialList_1 = materialList; _i < materialList_1.length; _i++) {
                        var material = materialList_1[_i];
                        if (material.key == 'rule') {
                            material.remarks = material.remarks.replace('活动公告：', '<b>活动公告：</b>');
                            material.remarks = material.remarks.replace('活动时间：', '<b>活动时间：</b>');
                            material.remarks = material.remarks.replace('活动对象：', '<b>活动对象：</b>');
                            material.remarks = material.remarks.replace('活动形式：', '<b>活动形式：</b>');
                            material.remarks = material.remarks.replace('游戏规则：', '<b>游戏规则：</b>');
                            material.remarks = material.remarks.replace('冲刺排行榜的小伙伴不要忘记填收货地址哦，大家加油冲呀！', '<b>冲刺排行榜的小伙伴不要忘记填收货地址哦，大家加油冲呀！</b>');
                            material.remarks = material.remarks.replace('弃奖说明：', '<b>弃奖说明：</b>');
                            material.remarks = material.remarks.replace('小编提示：', '<b>小编提示：</b>');
                            material.remarks = material.remarks.replace('奖励机制：', '<b>奖励机制：</b>');
                            material.remarks = material.remarks.replace('终极大奖：', '<b>终极大奖：</b>');
                            if (material.type == 'imgs') {
                                var imgs = material.imgs;
                                // console.log(imgs);
                                for (var i = 0; i < imgs.length; i++) {
                                    var element = imgs[i];
                                    // console.log(element);
                                    if (element.title && element.url) {
                                        material.remarks = material.remarks.replace('{{' + element.title + '}}', "<img src=\"".concat(element.url, "\">"));
                                    }
                                }
                            }
                            $('#mask-rule .scroll-y').html("<div class=\"text\">".concat(material.remarks, "</div>"));
                        }
                        else if (material.key == 'rank_info') {
                            //排行榜额外信息
                            rank_info = material.remarks;
                            $('#rank-info').click(function () {
                                weui.dialog({
                                    title: '排行榜说明',
                                    content: rank_info,
                                    className: 'custom-rankinfo',
                                    buttons: [{
                                            label: '我知道了',
                                            type: 'primary'
                                        }]
                                });
                            });
                        }
                        else if (material.key == 'prize_info') {
                            //奖品兑换额外信息
                            prize_info = material.remarks;
                        }
                        else if (material.key.indexOf('map_brand') >= 0) {
                            map_brand_info = material.imgs;
                        }
                        else if (material.key.indexOf('limit_phone') >= 0) {
                            limitPhone = material.imgs;
                        }
                        else if (material.key == 'diffculty') {
                            var list = material.imgs;
                            diffculty = list.map(function (item) { return item.num; });
                        }
                        else if (material.key == 'conins_config') {
                            var list = material.imgs;
                            conins_config = list;
                            $('#mask-game-continue .pannel .num').text(conins_config[2].num);
                        }
                        else if (material.key == 'home_adbtn') {
                            var list = material.imgs;
                            // console.log(list);
                            if (list && list.length > 0) {
                                $('#btn-goBuy').css('background-image', 'url(' + list[0].url + ')');
                                if (list[0].label) {
                                    $('#btn-goBuy').css('margin', list[0].label);
                                }
                                yiyuanBtnUrl = list[0].link;
                                $('#btn-yiyuanquan').attr('path', list[0].link);
                            }
                            // conins_config = list;
                            // $('#mask-game-continue .pannel .num').text(conins_config[2].num);
                        }
                    }
                    // console.log('map_brand_info', map_brand_info);
                    m_brand.init(map_brand_info);
                    //初始化任务情况
                    m_task.init(taskList, function () {
                        if (userData.unionid) {
                            //已授权会员卡，开放界面共同内容
                            $('#mask-rank .pannel-quanguo .scroll-y').css('height', virtualH - 190 - 212 - 100 - 250);
                            $.get(apiHost + '/api/client/spring2026/game/userinfo', {
                                gameCode: gameCode,
                                unionID: userData.unionid,
                            }, function (res) {
                                m_task.helpOthers();
                                window.game_user_info = res.data;
                                if (!window.game_user_info.name && localStorage.nickName) {
                                    //处理清数据后的缓存问题
                                    updateUserInfo();
                                }
                                // if (!res.data.avatar || !res.data.deptId) {
                                //没有头像或门店，则需要完善信息
                                //     updateUserInfo();
                                // }
                                m_points.drawMain();
                                if (gameInfo) {
                                    var startDate_1 = gameInfo.startDate, endtDate_1 = gameInfo.endtDate;
                                    var enrollmentTime = window.game_user_info.enrollmentTime;
                                    console.log(enrollmentTime, startDate_1, endtDate_1);
                                    if (new Date(enrollmentTime).valueOf() >= new Date(startDate_1).valueOf() &&
                                        new Date(enrollmentTime).valueOf() <= new Date(endtDate_1).valueOf()) {
                                        // todo: 完成注册任务后刷新任务
                                        m_task.updateTask(function () {
                                            m_task.successTask('newmember');
                                        });
                                    }
                                    else {
                                        // 老用户了
                                        $('#task-newmember').hide();
                                        m_task.updateTask();
                                    }
                                }
                                else {
                                    m_task.updateTask();
                                }
                            });
                        }
                        else {
                            var shareCardID = getCookie('shareCardID');
                            if (shareCardID) {
                                $('#mask-get-share-card .prize').attr('src', "./image/j2".concat(shareCardID, ".png"));
                                $('#mask-get-share-card').show();
                                $('#mask-get-share-card .main-btn').click(function () {
                                    weui.alert('您需要登录会员才能领取');
                                    goOauth();
                                });
                            }
                            //未授权登录会员
                            $('#mask-rank .pannel-quanguo .my-rank').hide();
                            $('#mask-rank .pannel-quanguo .scroll-y').css('height', virtualH - 200 - 100 - 250);
                            $('#mask-my-prize .item').hide();
                        }
                        $('#mask-rank .pannel-shenfen .scroll-y').css('height', virtualH - 200 - 100 - 250 - 54);
                    });
                }
                else {
                    weui.alert('游戏配置获取失败，请稍后再试~');
                }
            });
        },
        getRankInfo: function () {
            return rank_info || '';
        },
        getPrizeInfo: function () {
            return prize_info || '';
        },
        initGps: initGps,
        goOauth: goOauth,
        getDiffculty: function (cengshu) {
            var level = 0;
            curCengshu = cengshu;
            for (var i = 0; i < diffculty.length; i++) {
                var element = diffculty[i];
                if (cengshu >= element) {
                    level = i;
                }
                else {
                    break;
                }
            }
            m_brand.adview(curCengshu);
            return level;
        },
        checkChance: function (callback) {
            //检查剩余次数
            if (!userData.unionid) {
                //还不是会员，跳转
                weui.alert('您需要登录会员才能开始挑战');
                goOauth();
                return;
            }
            else {
                var totalChance = game_user_info.totalChance, totalPoint = game_user_info.totalPoint;
                if (totalChance < 1) {
                    return m_task.showTask();
                }
                game_user_info.totalChance--;
                game_user_info.useChance++;
                m_points.drawMain();
                thisRoundPrize = {
                    prize: null,
                    card: null,
                };
                $.post(apiHost + "/api/client/spring2026/game/lottery", {
                    gameCode: gameCode,
                    unionID: userData.unionid,
                }, function (res) {
                    if (res.code == 1) {
                        thisRoundPrize = res.data;
                        console.log(thisRoundPrize);
                    }
                });
                //开始游戏，记录福兔数
                thisRoundGet = {
                    prize: null,
                    card: null,
                    coins: 0,
                };
                setTimeout(function () {
                    updateProvinceData('add');
                }, 1000);
                callback && callback();
            }
        },
        getRoundPrize: function (prizeCallback, coinsCallback) {
            var getPrize = Math.random() < 0.5;
            var getCard = Math.random() > 0.7;
            //获取本轮奖品
            if (getPrize && thisRoundPrize.prize) {
                // $('#mask-get-prize .prize').attr('src', 'https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/image/j20.png');
                $.post(apiHost + "/api/client/spring2026/prize/unlock", {
                    gameCode: gameCode,
                    unionID: userData.unionid,
                    logid: thisRoundPrize.prize.id
                }, function (res) {
                    console.log('卡券解锁', res.data);
                });
                m_prize.refreshMyPrize();
                $('#mask-get-prize').show();
                thisRoundGet.prize = thisRoundPrize.prize;
                thisRoundPrize.prize = null;
                prizeCallback && prizeCallback();
            }
            else if (getCard && thisRoundPrize.card) {
                // $('#mask-get-prize .prize').attr('src', `./image/j2${thisRoundPrize.card.cardID}.png`);
                $.post(apiHost + "/api/client/spring2026/game/getcard", {
                    gameCode: gameCode,
                    unionID: userData.unionid,
                    cardID: thisRoundPrize.card.cardID
                }, function (res) {
                    console.log('获得菜品卡', res.data);
                });
                m_card.refreshMyCard();
                $('#mask-get-prize').show();
                thisRoundGet.card = thisRoundPrize.card;
                thisRoundPrize.card = null;
                prizeCallback && prizeCallback();
            }
            else {
                var getCoinsNum = randomNum(conins_config[0].num, conins_config[1].num);
                // console.log(diffculty, conins_config);
                $.post(apiHost + "/api/client/spring2026/game/getConins", {
                    gameCode: gameCode,
                    unionID: userData.unionid,
                    conins: getCoinsNum
                }, function (res) {
                    console.log('获得金币', res.data);
                });
                thisRoundGet.coins += getCoinsNum;
                game_user_info.totalCoins += getCoinsNum;
                m_points.drawMain();
                coinsTipsTimer && clearTimeout(coinsTipsTimer);
                $('.coins-tips').text('金币 +' + getCoinsNum).show();
                coinsTipsTimer = setTimeout(function () {
                    $('.coins-tips').hide();
                }, 1200);
                coinsCallback && coinsCallback(getCoinsNum);
            }
        },
        endRound: function () {
            return thisRoundGet;
        },
        useCoins: function (callback) {
            var continueCoins = conins_config[2].num;
            if (game_user_info.totalCoins >= -1 * continueCoins) {
                //注意这里是负数
                game_user_info.totalCoins += continueCoins;
                m_points.drawMain();
                $.post(apiHost + "/api/client/spring2026/game/useConins", {
                    gameCode: gameCode,
                    unionID: userData.unionid,
                }, function (res) {
                    console.log('使用金币', res.data);
                });
                callback && callback();
            }
            else {
                $('.coins-tips').text('金币不足').show();
                coinsTipsTimer = setTimeout(function () {
                    $('.coins-tips').hide();
                }, 1200);
            }
        }
    };
})();
var m_task = (function () {
    var myTaskList = [];
    var isClickWxappLanuch = false;
    var isClickWxappLanuchVideo = false;
    var needMyTask = true;
    var taskViewUrl = "/subGoods/pages/activityDecorate/activityDecorate?activityConfigId=1264548200331403264&utm_source=tyt";
    var taskVideoUrl = "/__plugin__/wx2b03c6e691cd7370/pages/live-player-plugin?room_id=231&utm_source=tytnhj";
    var updateTask = function (callback) {
        if (callback === void 0) { callback = function () { }; }
        globalLoading.show();
        $.get(apiHost + '/api/client/spring2026/task/mylog', {
            gameCode: gameCode,
            unionID: userData.unionid,
            pageNo: 1,
            pageSize: 450,
            findAll: 'findAll'
        }, function (res) {
            globalLoading.hide();
            var pageList = res.data.pageList;
            // console.log(res);
            var todayStart = new Date();
            todayStart.setHours(0);
            todayStart.setMinutes(0);
            todayStart.setSeconds(0);
            for (var i = 0; i < myTaskList.length; i++) {
                var task = myTaskList[i];
                task.finishedNum = 0;
                task.finishedAllNum = 0;
                for (var j = 0; j < pageList.length; j++) {
                    var tasklog = pageList[j];
                    if (tasklog.taskID == task.id) {
                        task.finishedAllNum++;
                        if (new Date(tasklog.ctime).valueOf() >= todayStart.valueOf()) {
                            task.finishedNum++;
                        }
                    }
                }
                var taskKey = findTaskKey(task);
                console.log(task.name, task.finishedNum, task.dailylimit, task.finishedAllNum, task.totallimit);
                if (task.finishedAllNum >= task.totallimit) {
                    //超过可完成全部可极限了
                    $("#task-".concat(taskKey, " .number s")).text(task.finishedAllNum);
                    disableTask(taskKey);
                    continue;
                }
                // if (taskKey == 'score') {
                //     //这里是总次数
                //     $(`#task-${taskKey} .number s`).text(task.finishedAllNum);
                // } else {
                //这里是每日次数
                $("#task-".concat(taskKey, " .number s")).text(task.finishedNum);
                // }
                if (task.finishedNum >= task.dailylimit) {
                    //超过可完成极限了
                    disableTask(taskKey);
                }
            }
            callback && callback();
        });
    };
    var showTask = function (addFixed) {
        // if (!needMyTask) {
        //     //不需要刷新数据
        //     return;
        // }
        // needMyTask = false;
        if (addFixed === void 0) { addFixed = true; }
        //刷新用户次数
        $.get(apiHost + '/api/client/spring2026/game/userinfo', {
            gameCode: gameCode,
            unionID: userData.unionid,
        }, function (res) {
            window.game_user_info = res.data;
            m_points.drawMain();
            updateTask();
            if (addFixed) {
                $('#mask-task').show().addClass('fixed');
            }
        });
    };
    $('#mask-task .close').click(function () {
        $('#mask-task').removeClass('fixed');
    });
    $('.btn-goOauth').click(function () {
        m_game.goOauth();
    });
    $('#task-order .btn-canget').click(function () {
        m_game.initGps(function () {
            $("#mask-choice-store").show().removeClass('can-appointment');
        }, true);
    });
    $('#task-score .btn-canget').click(function () {
        if (game_user_info && game_user_info.memberId) {
            globalLoading.show();
            var url = 'https://yx.lbxcn.com/japi/lbx/getscore';
            if (isDev) {
                url = 'https://muyang.hn.cn/japi/lbx/getscore';
            }
            $.post(url, {
                member_id: game_user_info.memberId
            }, function (resStr) {
                console.log(resStr);
                var res = {};
                try {
                    res = JSON.parse(resStr);
                }
                catch (error) {
                }
                if (res.code == 0 && res.data && res.data.length > 0) {
                    var current_bonus = res.data[0].current_bonus;
                    console.log(current_bonus);
                    if (current_bonus >= 10) {
                        successTask('score', function () {
                            globalLoading.hide();
                            var url = 'https://yx.lbxcn.com/japi/lbx/usescore2026';
                            if (isDev) {
                                url = 'https://muyang.hn.cn/japi/lbx/usescore2026';
                            }
                            $.post(url, {
                                member_id: game_user_info.memberId,
                                integral: 10,
                                seq_id: new Date().valueOf(),
                            }, function (res) {
                                $('.coins-tips').text('兑换成功').show();
                                var coinsTipsTimer = setTimeout(function () {
                                    $('.coins-tips').hide();
                                }, 1200);
                                console.log(res);
                            });
                        });
                    }
                    else {
                        globalLoading.hide();
                        weui.alert('很遗憾，您的积分不足~<br />当前积分：' + current_bonus);
                    }
                }
                else {
                    globalLoading.hide();
                    weui.alert('系统异常，请稍后再试~');
                }
            });
        }
        else {
            m_game.goOauth();
        }
    });
    var findTask = function (taskKey) {
        for (var i = 0; i < myTaskList.length; i++) {
            var task = myTaskList[i];
            if (taskKey === 'view' && task.name == '浏览会场') {
                return task;
            }
            if (taskKey === 'share' && task.name == '邀请好友一起玩') {
                return task;
            }
            if (taskKey === 'login' && task.name == '每日登录') {
                return task;
            }
            if (taskKey === 'newmember' && task.name == '新注册会员') {
                return task;
            }
            if (taskKey === 'buy' && task.name == '购买一元券') {
                return task;
            }
            if (taskKey === 'order' && task.name == '到店消费') {
                return task;
            }
            if (taskKey === 'score' && task.name == '积分兑换') {
                return task;
            }
            if (taskKey === 'video' && task.name == '订阅直播') {
                return task;
            }
        }
        return null;
    };
    var findTaskKey = function (task) {
        var taskKey = '';
        if (task.name == '浏览会场') {
            taskKey = 'view';
        }
        else if (task.name == '邀请好友一起玩') {
            taskKey = 'share';
        }
        else if (task.name == '每日登录') {
            taskKey = 'login';
        }
        else if (task.name == '购买一元券') {
            taskKey = 'buy';
        }
        else if (task.name == '新注册会员') {
            taskKey = 'newmember';
        }
        else if (task.name == '到店消费') {
            taskKey = 'order';
        }
        else if (task.name == '积分兑换') {
            taskKey = 'score';
        }
        else if (task.name == '订阅直播') {
            taskKey = 'video';
        }
        return taskKey;
    };
    var disableTask = function (taskKey) {
        if (taskKey === 'login') {
            $("#task-".concat(taskKey, " .btn")).text('已登录');
        }
        else if (taskKey === 'view') {
            $("#task-".concat(taskKey, " .btn")).text('已签到');
        }
        else if (taskKey === 'share') {
            $("#task-".concat(taskKey, " .btn")).text('已分享');
        }
        else if (taskKey === 'buy') {
            $("#task-".concat(taskKey, " .btn")).text('已购买');
        }
        else if (taskKey === 'newmember') {
            $("#task-".concat(taskKey, " .btn")).text('已注册');
        }
        else if (taskKey === 'order') {
            $("#task-".concat(taskKey, " .btn")).text('已消费');
        }
        else if (taskKey === 'score') {
            $("#task-".concat(taskKey, " .btn")).text('已兑完');
        }
        else if (taskKey === 'video') {
            $("#task-".concat(taskKey, " .btn")).text('已订阅');
        }
        $("#task-".concat(taskKey, " .btn")).removeClass('btn-canget').addClass('btn-wasget');
    };
    var successTask = function (taskKey, callback) {
        if (callback === void 0) { callback = function () { }; }
        var task = findTask(taskKey);
        var id = task.id;
        if (taskKey == 'newmember') {
            console.log('newmember', myTaskList);
            for (var i = 0; i < myTaskList.length; i++) {
                var tasklog = myTaskList[i];
                if (tasklog.name == "新注册会员") {
                    return;
                }
            }
        }
        if (task.finishedNum < task.dailylimit && task.finishedAllNum < task.totallimit) {
            //可以完成任务
            addChance(id, function () {
                callback && callback();
                task.finishedNum++;
                task.finishedAllNum++;
                $("#task-".concat(taskKey, " .number s")).text(task.finishedNum);
                game_user_info.totalPoint += task.point;
                game_user_info.totalCoins += task.coins;
                game_user_info.totalChance += task.chance;
                m_points.drawMain();
                if (task.finishedNum >= task.dailylimit ||
                    task.finishedAllNum >= task.totallimit) {
                    //超过可完成极限了
                    disableTask(taskKey);
                }
            });
        }
    };
    var addChance = function (taskID, callback) {
        globalLoading.show();
        $.post(apiHost + '/api/client/spring2026/task/log', {
            gameCode: gameCode,
            openID: userData.openID,
            unionID: userData.unionid,
            taskID: taskID,
            type: "success",
        }, function (res) {
            globalLoading.hide();
            setTimeout(function () {
                console.log('完成任务', res);
                if (res.code == 1) {
                    callback && callback();
                }
                else {
                    weui.alert(res.message);
                }
            }, 300);
        });
    };
    var failTask = function (taskKey) {
        var task = findTask(taskKey);
        var taskID = task.id;
        globalLoading.show();
        $.post(apiHost + '/api/client/spring2026/task/log', {
            gameCode: gameCode,
            openID: userData.openID,
            unionID: userData.unionid,
            taskID: taskID,
            type: "fail",
        }, function (res) {
            globalLoading.hide();
            task.finishedNum++;
            $("#task-".concat(taskKey, " .number s")).text(task.finishedNum);
            if (task.finishedNum >= task.dailylimit) {
                //超过可完成极限了
                disableTask(taskKey);
            }
        });
    };
    return {
        init: function (list, callback) {
            $('#task-score .num').html('10分/次-已兑换：<span class="number"><s>0</s>/<b></b></span>次');
            if (new Date().valueOf() >= new Date('2024/01/18 00:00:00').valueOf()) {
                $('#task-buy').hide();
            }
            if (new Date().valueOf() >= new Date('2024/01/29 00:00:00').valueOf()) {
                $('#task-video').hide();
            }
            myTaskList = list;
            for (var i = 0; i < myTaskList.length; i++) {
                var task = myTaskList[i];
                var taskKey = findTaskKey(task);
                $("#task-".concat(taskKey, " .task-reward span")).text('+' + task.chance);
                $("#task-".concat(taskKey, " .number b")).text(task.dailylimit);
                if (task.defaultImg) {
                    $("#task-".concat(taskKey, " .icon")).css('background-image', "url(".concat(task.defaultImg, ")"));
                }
                $("#task-".concat(taskKey, " .btn")).data('id', task.id);
                if (task.name == "浏览会场" && task.remarks) {
                    //特定日期要跳转不同会场
                    try {
                        var obj = JSON.parse(task.remarks);
                        $("#task-".concat(taskKey, " .info h1")).text(obj.text);
                        taskViewUrl = obj.path;
                        $('#launch-view').attr('path', taskViewUrl);
                    }
                    catch (error) {
                    }
                }
                else if (task.name == "订阅直播" && task.remarks) {
                    //特定日期要跳转不同直播
                    try {
                        var obj = JSON.parse(task.remarks);
                        $("#task-".concat(taskKey, " .info h1")).text(obj.text);
                        taskVideoUrl = obj.path;
                        $('#launch-video').attr('path', taskVideoUrl);
                    }
                    catch (error) {
                    }
                }
                else if (task.remarks) {
                    //特定日期要跳转不同会场
                    try {
                        var obj = JSON.parse(task.remarks);
                        $("#task-".concat(taskKey, " .info h1")).text(obj.text);
                    }
                    catch (error) {
                    }
                }
            }
            if (userData.openID && userData.unionid) {
                var task = findTask('login');
                // console.log(task);
                if (task && today.str1 != localStorage.loginDate) {
                    //如果今天没签到，则完成每日签到任务
                    localStorage.loginDate = today.str1;
                    var taskID = task.id;
                    $.post(apiHost + '/api/client/spring2026/task/log', {
                        gameCode: gameCode,
                        openID: userData.openID,
                        unionID: userData.unionid,
                        taskID: taskID,
                        type: "success",
                    }, function (res) {
                        callback && callback();
                    });
                }
                else {
                    callback && callback();
                }
            }
            else {
                callback && callback();
            }
        },
        showTask: showTask,
        successTask: successTask,
        failTask: failTask,
        findTask: findTask,
        updateTask: updateTask,
        helpOthers: function () {
            var shareUnionID = getCookie('shareUnionID');
            if (shareUnionID && shareUnionID !== 'undefined' && shareUnionID !== userData.unionid) {
                var shareCardID_1 = getCookie('shareCardID');
                if (shareCardID_1 && !localStorage.getItem("s-".concat(shareCardID_1, "-").concat(shareUnionID))) {
                    $('#mask-get-share-card .prize').attr('src', "./image/j2".concat(shareCardID_1, ".png"));
                    $('#mask-get-share-card').show();
                    $('#mask-get-share-card .main-btn').click(function () {
                        //已登录
                        globalLoading.show();
                        $.post(apiHost + "/api/client/spring2026/game/getOtherCard", {
                            gameCode: gameCode,
                            shareUnionID: shareUnionID,
                            joinUnionID: userData.unionid,
                            shareCardID: shareCardID_1,
                        }, function (res) {
                            globalLoading.hide();
                            if (res.code == 1) {
                                console.log('领取成功');
                                weui.alert(res.message);
                                setCookie('shareCardID', '');
                                localStorage.setItem("s-".concat(shareCardID_1, "-").concat(shareUnionID), '1');
                                $('#mask-get-share-card').hide();
                            }
                            else {
                                weui.alert(res.message);
                            }
                        });
                    });
                }
                //是别人分享过来的，则给它增加一次，并清除此次关联，防止后续关联
                var shareOpenID_1 = getCookie('shareOpenID');
                setCookie('shareUnionID', '');
                setCookie('shareOpenID', '');
                //保存被分享人打开的信息
                $.post(apiHost + "/api/client/spring2026/user/helpOthers", {
                    gameCode: gameCode,
                    shareOpenID: shareOpenID_1,
                    shareUnionID: shareUnionID,
                    joinOpenID: userData.openID,
                    joinUnionID: userData.unionid,
                    joinName: userData.nickName || localStorage.nickName || '',
                    joinAvatar: userData.headimgurl || localStorage.headimgurl || '',
                    cardID: shareCardID_1 || '',
                }, function (res) {
                    if (res.code == 1) {
                        var task = findTask('share');
                        var taskID = task.id;
                        $.post(apiHost + '/api/client/spring2026/task/log', {
                            gameCode: gameCode,
                            openID: shareOpenID_1,
                            unionID: shareUnionID,
                            taskID: taskID,
                            type: "success",
                        }, function (res) {
                            console.log('为他人助力成功', res.data);
                        });
                    }
                });
            }
        },
        initWxappViewBtn: function () {
            if (plat == 'wxapp') {
                $('#btn-goZhuanchang').click(function () {
                    wx.miniProgram.navigateTo({
                        url: "/subGoods/pages/activityDecorate/activityDecorate?activityConfigId=1538603537153355776&utm_source=tyt",
                        success: function (res) {
                            successTask('view');
                        }
                    });
                });
                //签到任务
                $('#task-view .btn').click(function () {
                    wx.miniProgram.navigateTo({
                        url: taskViewUrl,
                        success: function (res) {
                            successTask('view');
                        }
                    });
                });
                $('#task-video .btn').click(function () {
                    wx.miniProgram.navigateTo({
                        url: taskVideoUrl,
                        success: function (res) {
                            successTask('video');
                        }
                    });
                });
                //购买一元券
                $('#task-buy .btn').click(function () {
                    wx.miniProgram.navigateTo({
                        url: "/activity/pages/myCoupon/myCoupon?type=1&utm=game",
                        success: function (res) {
                        }
                    });
                });
                $('#btn-goBuy').click(function () {
                    wx.miniProgram.navigateTo({
                        url: yiyuanBtnUrl,
                        success: function (res) {
                        }
                    });
                });
            }
            else {
                var viewBtn = document.getElementById('launch-view');
                viewBtn.addEventListener('launch', function (e) {
                    isClickWxappLanuch = true;
                    console.log('小程序启动launch', isClickWxappLanuch, e);
                });
                var viewBtn2 = document.getElementById('launch-video');
                viewBtn2.addEventListener('launch', function (e) {
                    isClickWxappLanuchVideo = true;
                    console.log('小程序启动launch video', isClickWxappLanuchVideo, e);
                });
            }
        },
        comeBackH5: function () {
            console.log('小程序切换回来', isClickWxappLanuch, isClickWxappLanuchVideo);
            if (isClickWxappLanuch) {
                isClickWxappLanuch = false;
                successTask('view');
            }
            if (isClickWxappLanuchVideo) {
                isClickWxappLanuchVideo = false;
                successTask('video');
            }
        }
    };
})();
var m_points = (function () {
    var myRankNo = 0;
    //打开排行榜
    var needRankData = true;
    var getRankData = function (needRender) {
        if (needRender === void 0) { needRender = true; }
        if (!needRankData) {
            //不需要刷新排行榜数据
            return;
        }
        needRankData = false;
        globalLoading.show();
        var params = {
            gameCode: gameCode,
            sort: 'totalPoint',
        };
        if (window.game_user_info && window.game_user_info.totalPoint) {
            params.totalPoint = window.game_user_info.totalPoint;
            params.unionID = window.game_user_info.unionID;
        }
        $.get(apiHost + '/api/client/spring2026/user/pointrank', params, function (res) {
            globalLoading.hide();
            console.log(res);
            var _a = res.data, pageList = _a.pageList, pageList2 = _a.pageList2, totalCount = _a.totalCount, realRank = _a.realRank;
            var htmlStr = '';
            var gapNum = 0;
            for (var i = 0; i < pageList.length; i++) {
                var element = pageList[i];
                var no = i + 1;
                if (i < 3) {
                    no = "<img src=\"https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/d3".concat(no, ".png\" />");
                }
                htmlStr += "<div class=\"item\">\n                    <div class=\"no\">".concat(no, "</div>\n                    <div class=\"name\">\n                        <img class=\"avatar\" src=\"").concat(element.avatar, "\" alt=\"\">\n                        <div class=\"text\">").concat(element.name, "</div>\n                    </div>\n                    <div class=\"coins\">").concat(element.totalPoint, "</div>\n                </div>");
                if (window.game_user_info && game_user_info.unionID == element.unionID) {
                    console.log('已登录，在排行榜中');
                    // myRankNo = i + 1;
                    if (i > 0) {
                        gapNum = pageList[i - 1].totalPoint - element.totalPoint;
                    }
                }
            }
            if (window.game_user_info) {
                // if (myRankNo == 0) {
                //     console.log('已登录，但不在排行中')
                //     if (game_user_info.totalPoint == 0) {
                //         myRankNo = totalCount + 1;
                //     } else {
                //         const lastOneCoins = pageList[pageList.length - 1].totalPoint;
                //         const gapCoins = lastOneCoins - game_user_info.totalPoint;
                //         // console.log(lastOneCoins, gapCoins);
                //         myRankNo = parseInt(pageList.length + (totalCount - pageList.length) * (gapCoins / lastOneCoins));
                //     }
                //     gapNum = 10;
                // }
                // console.log(realRank, myRankNo);
                // if (realRank && myRankNo < 20) {
                //     myRankNo = realRank;
                // }
                // if (realRank && realRank < myRankNo) {
                //     myRankNo = realRank;
                // }
                // $('.myRankNo').text(myRankNo)
                // if (myRankNo > 1) {
                //     $('.gap-div').html(`距离上一名仅差<span class="gap">${gapNum}</span>个金币`)
                // } else {
                //     $('.gap-div').html(`加油！继续保持！`)
                // }
                myRankNo = realRank;
                $('.myRankNo').text(myRankNo);
                if (pageList2 && pageList2.length > 0) {
                    for (var i = 0; i < pageList2.length; i++) {
                        var element = pageList2[i];
                        var no = realRank - pageList2.length + i + 1;
                        htmlStr += "<div class=\"item\">\n                                        <div class=\"no\">".concat(no, "</div>\n                                        <div class=\"name\">\n                                            <img class=\"avatar\" src=\"").concat(element.avatar, "\" alt=\"\">\n                                            <div class=\"text\">").concat(element.name, "</div>\n                                        </div>\n                                        <div class=\"coins\">").concat(element.totalPoint, "</div>\n                                    </div>");
                    }
                }
                if (!localStorage.saveAddress && myRankNo <= 1500 && game_user_info.totalPoint > 0) {
                    weui.dialog({
                        title: '恭喜上榜',
                        content: '您的排名已进入前1500，如活动结束仍然上榜将为您邮寄奖品，请在活动结束前填写您的收件地址。',
                        className: 'custom-classname',
                        buttons: [{
                                label: '稍后再填',
                                type: 'default',
                                onClick: function () {
                                }
                            }, {
                                label: '立即填写',
                                type: 'primary',
                                onClick: function () {
                                    m_prize.fillRankAddress();
                                }
                            }]
                    });
                }
            }
            if (needRender) {
                if (m_game.getRankInfo()) {
                    htmlStr += '<p class="extra-tips">' + m_game.getRankInfo() + '</p>';
                }
                $('#mask-rank .pannel-quanguo .rank-list .scroll-y').html(htmlStr);
            }
        });
    };
    $('#btn-saveAddress').click(function () {
        if (myRankNo <= 1500 && game_user_info && game_user_info.totalPoint > 0) {
            m_prize.fillRankAddress();
        }
        else {
            weui.alert('抱歉，您暂未上榜');
        }
    });
    $('.province').click(function () {
        $('#mask-rank .pannel-quanguo').hide();
        // $('#mask-rank .d21').hide();
        $('#mask-rank .pannel-shenfen').show();
        // $('#mask-rank .d22').show();
        getRankData(true);
    });
    $('.btn-rank').click(function () {
        $('#mask-rank .pannel-quanguo').show();
        // $('#mask-rank .d21').show();
        $('#mask-rank .pannel-shenfen').hide();
        // $('#mask-rank .d22').hide();
        getRankData(true);
        alert('在活动日最后一天2026年2月28日23:59:59后，系统将在3天内完成所有异常数据清洗，如有疑问请与客服联系。最终核算准确数据后，以最新排行榜数据为准！请准确填写收件地址，3天后将无法更改收件地址！');
    });
    var needProvinceRank = true;
    var getProvinceRank = function (needRender, callback) {
        if (needRender === void 0) { needRender = true; }
        if (!needProvinceRank) {
            return;
        }
        needProvinceRank = false;
        globalLoading.show();
        $.get(apiHost + '/api/client/spring2026/count/detail', {
            gameCode: gameCode,
        }, function (res) {
            globalLoading.hide();
            // return;
            var _a = res.data, list = _a.list, incrementNumber = _a.incrementNumber, realNumber = _a.realNumber, virtualNumber = _a.virtualNumber;
            var htmlStr = '';
            list.map(function (item) {
                item.totalNum = item.realNumber + item.incrementNumber + item.virtualNumber;
            });
            list.sort(function (a, b) { return b.totalNum - a.totalNum; });
            for (var i = 0; i < list.length && i < 20; i++) {
                var element = list[i];
                var no = i + 1;
                if (i < 3) {
                    no = "<img src=\"https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/d3".concat(no, ".png\" />");
                }
                htmlStr += "<div class=\"item\">\n                    <div class=\"no\">".concat(no, "</div>\n                    <div class=\"name\">\n                        <div class=\"text\">").concat(getCodeValue(element.province), "</div>\n                    </div>\n                    <div class=\"coins\">").concat(element.totalNum, "</div>\n                </div>");
            }
            htmlStr += '<p class="extra-tips">省份排行榜每小时更新一次</p>';
            $('#mask-rank .pannel-shenfen .rank-list .scroll-y').html(htmlStr);
            callback && callback(incrementNumber + realNumber + virtualNumber);
        });
    };
    $('#mask-rank .tab-btn div').click(function () {
        $('#mask-rank .tab-btn div').removeClass('active');
        $(this).addClass('active');
        if ($(this).hasClass('quanguo')) {
            $('#mask-rank .pannel-quanguo').show();
            $('#mask-rank .d21').show();
            $('#mask-rank .pannel-shenfen').hide();
            $('#mask-rank .d22').hide();
            getRankData(true);
        }
        else {
            $('#mask-rank .pannel-quanguo').hide();
            $('#mask-rank .d21').hide();
            $('#mask-rank .pannel-shenfen').show();
            $('#mask-rank .d22').show();
            getProvinceRank(true, null);
        }
    });
    var drawMain = function () {
        console.log(game_user_info);
        var totalCoins = game_user_info.totalCoins, totalChance = game_user_info.totalChance, useChance = game_user_info.useChance, totalPoint = game_user_info.totalPoint;
        $('.totalChance').text(totalChance);
        $('.useChance').text(useChance);
        $('.totalPoint').text(totalPoint);
        $('.totalCoins').text(totalCoins);
        //渲染一次，存档一次
        localStorage.game_user_info = JSON.stringify(game_user_info);
    };
    return {
        getRankData: getRankData,
        drawMain: drawMain,
        savePoints: function (step, t) {
            game_user_info.totalPoint += step;
            $.post(apiHost + "/api/client/spring2026/game/step", {
                gameCode: gameCode,
                unionID: userData.unionid,
                step: step,
                t: t
            }, function (res) {
                console.log('保存跳跃层数', step, res.data);
            });
            needRankData = true;
            drawMain();
        },
        getProvinceRank: getProvinceRank,
    };
})();
var m_prize = (function () {
    // 兑换与领奖相关
    var getZoumadeng = function () {
        $.get(apiHost + '/api/client/spring2026/prize/log', {
            gameCode: gameCode,
            pageNo: 1,
            pageSize: 50,
        }, function (res) {
            var _a = res.data, pageList = _a.pageList, totalCount = _a.totalCount;
            var htmlStr = '';
            for (var i = 0; i < pageList.length; i++) {
                var item = pageList[i];
                htmlStr += "<div>\u606D\u559C ".concat(item.name, " \u83B7\u5F97 ").concat(item.prizeName, "</div>");
                // ${new Date(item.ctime).Format("yyyy-MM-dd hh:mm")}
            }
            $('.zoumadeng').html(htmlStr);
            var prev = -1;
            var cur = 0;
            var $prizelogList = $('.zoumadeng div');
            if ($prizelogList.length > 1) {
                $prizelogList.eq(cur).addClass('enter');
                prev = cur;
                cur++;
                setInterval(function () {
                    $prizelogList.eq(prev).addClass('leave');
                    var tempJoin = prev;
                    setTimeout(function () {
                        $prizelogList.eq(tempJoin).removeClass('enter leave');
                    }, 1000);
                    $prizelogList.eq(cur).addClass('enter');
                    prev = cur;
                    cur++;
                    if (cur >= $prizelogList.length) {
                        cur = 0;
                    }
                }, 4000);
            }
            else {
                //只有一条
                $prizelogList.eq(0).addClass('enter');
            }
        });
    };
    //打开兑奖页面
    var needPrizeData = true;
    var coinsTipsTimer = null;
    var getPrizeData = function () {
        if (!needPrizeData)
            return;
        // needPrizeData = false;
        var prizeList = [];
        var bindClick = function () {
            $('#mask-exchange-prize .scroll-y .item .btn').click(function () {
                var $btn = $(this);
                var i = $('#mask-exchange-prize .scroll-y .item .btn').index($btn);
                var prize = prizeList[i];
                console.log(prize);
                var getPrize = function (callback) {
                    globalLoading.show();
                    $.post("".concat(apiHost, "/api/client/spring2026/prize/log"), {
                        gameCode: gameCode,
                        unionID: userData.unionid,
                        prizeID: prize.id
                    }, function (res) {
                        globalLoading.hide();
                        console.log(res);
                        if (res.code == 1) {
                            weui.alert('兑换成功');
                            prize.wasget++;
                            prize.allowNum--;
                            var $itemDom = $('#mask-exchange-prize .scroll-y .item').eq(i);
                            $itemDom.find('.num').text('库存：' + prize.allowNum);
                            if (prize.wasget >= prize.userMaxGetNum) {
                                console.log('已经兑换过，且超过可兑换最大数字');
                                $btn.addClass('wasget');
                                $btn.children('img').attr('src', "https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/image/k22.png");
                            }
                            needMyPrize = true;
                            callback && callback();
                        }
                        else {
                            weui.alert(res.message);
                        }
                    });
                };
                if (prize.type > 20) {
                    //十全大奖
                    if (m_card.getHasNum() >= 10) {
                        getPrize(function () {
                            m_card.refreshMyCard();
                            m_card.getMyCard();
                        });
                    }
                    else {
                        weui.alert('需集齐10个菜品方可兑换，您还需要' + (10 - m_card.getHasNum()) + '个菜品');
                    }
                }
                else {
                    if (game_user_info.totalCoins >= prize.needCoins) {
                        getPrize(function () {
                            game_user_info.totalCoins -= prize.needCoins;
                            m_points.drawMain();
                        });
                    }
                    else {
                        $('.coins-tips').text('金币不足').show();
                        coinsTipsTimer && clearTimeout(coinsTipsTimer);
                        coinsTipsTimer = setTimeout(function () {
                            $('.coins-tips').hide();
                        }, 1200);
                    }
                }
            });
        };
        var render = function () {
            $.get(apiHost + '/api/client/spring2026/prize', {
                gameCode: gameCode,
                pageNo: 1,
                pageSize: 10,
            }, function (res) {
                var _a = res.data, pageList = _a.pageList, totalCount = _a.totalCount;
                prizeList = pageList;
                var htmlStr = '';
                for (var i = 0; i < pageList.length; i++) {
                    var prize = pageList[i];
                    var btn = '';
                    if (window.game_user_info) {
                        btn = "<div class=\"btn\">\n                            <img src=\"https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/image/k2.png\" alt=\"\">\n                        </div>";
                    }
                    prize.wasget = 0;
                    if (myPrizeLog.length > 0) {
                        //有奖品
                        for (var j = 0; j < myPrizeLog.length; j++) {
                            var log = myPrizeLog[j];
                            if (log.prizeID == prize.id) {
                                prize.wasget++;
                            }
                        }
                        if (prize.wasget >= prize.userMaxGetNum) {
                            console.log('已经兑换过，且超过可兑换最大数字');
                            btn = "<div class=\"btn wasget\">\n                                <img src=\"https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/image/k22.png\" alt=\"\">\n                            </div>";
                        }
                    }
                    if (prize.type > 20) {
                        var fontSizeStyle = '';
                        console.log(prize.name, prize.name.length);
                        if (prize.name.length > 7) {
                            fontSizeStyle = ' style="font-size: 24px;" ';
                        }
                        htmlStr += "<div class=\"item sp\">\n                            <div class=\"icon\" style=\"background-image: url('".concat(prize.defaultImg, "!thumb');\"></div>\n                            <div class=\"info\">\n                                <div class=\"name\" ").concat(fontSizeStyle, ">").concat(prize.name, "</div>\n                                <div class=\"tips\">\u5151\u6362\u6761\u4EF6\uFF1A\u96C6\u9F50\u5341\u6B3E<br />\u4E0D\u540C\u83DC\u54C1 \n                                    <div class=\"need-coins\">    \n                                        <img src=\"https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/image/g21.png\" alt=\"\">\n                                        ").concat(m_card.getHasNum(), " / 10 \n                                    </div>\n                                </div>\n                                <div class=\"num\">").concat(prize.allowNum > 0 ? '库存：' + prize.allowNum : '奖品已兑完', "</div>\n                            </div>\n                            ").concat(prize.allowNum > 0 ? btn : '', "\n                        </div>");
                    }
                    else {
                        htmlStr += "<div class=\"item\">\n                            <div class=\"icon\" style=\"background-image: url('".concat(prize.defaultImg, "!thumb');\"></div>\n                            <div class=\"info\">\n                                <div class=\"name\">").concat(prize.name, "</div>\n                                <div class=\"num\">").concat(prize.allowNum > 0 ? '库存：' + prize.allowNum : '奖品已兑完', "</div>\n                                <div class=\"need-coins\">\n                                    <img src=\"https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/01lbxnhj/img/icon_jb.png\" alt=\"\">\n                                    <span class=\"num\">").concat(prize.needCoins, "</span>\n                                </div>\n                            </div>\n                            ").concat(prize.allowNum > 0 ? btn : '', "\n                        </div>");
                    }
                }
                if (totalCount <= 0) {
                    htmlStr = "<div class=\"empty\">\n                        \u6682\u65E0\u53EF\u5151\u6362\u5956\u54C1\n                    </div>";
                }
                else {
                    if (m_game.getPrizeInfo()) {
                        htmlStr += '<p class="extra-tips">' + m_game.getPrizeInfo() + '</p>';
                    }
                }
                $('#mask-exchange-prize .scroll-y').html(htmlStr);
                bindClick();
                setTimeout(function () {
                    globalLoading.hide();
                }, 300);
            });
        };
        globalLoading.show();
        if (window.game_user_info && myPrizeLog.length <= 0) {
            //已登录，且未获取我的奖品，则获取
            getMyPrize(function () {
                render();
            });
        }
        else {
            render();
        }
    };
    $('.show-mask[data-mask="exchange-prize"]').click(function () {
        getPrizeData();
    });
    var myPrizeLog = [];
    var needMyPrize = true;
    var rankPrizeLog = null;
    var getMyPrize = function (callback) {
        if (!needMyPrize) {
            //不需要刷新数据
            callback && callback();
            return;
        }
        needMyPrize = false;
        // m_game.initGps((shop_id) => {
        globalLoading.show();
        var couponDom = $('#mask-my-prize .scroll-y .coupon');
        var physicalDom = $('#mask-my-prize .scroll-y .physical');
        couponDom.hide();
        physicalDom.hide();
        $.get(apiHost + '/api/client/spring2026/prize/log', {
            gameCode: gameCode,
            unionID: userData.unionid,
            pageNo: 1,
            pageSize: 50,
        }, function (res) {
            globalLoading.hide();
            var couponCur = 0;
            var physicaCur = 0;
            var _a = res.data, pageList = _a.pageList, totalCount = _a.totalCount;
            myPrizeLog = pageList;
            couponDom.hide();
            physicalDom.hide();
            //   label: "抽奖-实物奖品", value: 1
            //   label: "抽奖-线下优惠券", value: 2
            //   label: "抽奖-线上优惠券", value: 3
            //   label: "兑换-实物奖品", value: 11
            //   label: "兑换-线下优惠券", value: 12
            //   label: "兑换-线上优惠券", value: 13
            //   label: "兑换-十全大奖", value: 21
            var htmlStr = '';
            var couponValue = [2, 3, 12, 13];
            for (var i = 0; i < pageList.length; i++) {
                var prizelog = pageList[i];
                if (prizelog.type == 99) {
                    rankPrizeLog = prizelog;
                    continue;
                }
                var curDom = null;
                if (couponValue.indexOf(prizelog.prizeType) >= 0) {
                    var couponType = [2, 12].indexOf(prizelog.prizeType) >= 0 ? 1 : 2;
                    var path = "activity/pages/myCoupon/myCoupon?type=".concat(couponType);
                    if (prizelog.cardInfo && prizelog.cardInfo.path) {
                        path = prizelog.cardInfo.path;
                    }
                    var env = 'env-version="trial"';
                    // if (location.host.indexOf('lbxcn.com') >= 0) {
                    env = '';
                    // }
                    var wxh5btn = (plat == 'wxapp') ? '' : "<wx-open-launch-weapp id=\"launch-btn".concat(prizelog.id, "\" ").concat(env, " username=\"gh_e1ccacf348ed\"\n                                                                    path=").concat(path, ">\n                                                                    <template>\n                                                                        <style>\n                                                                            .open-wxapp-btn3 {\n                                                                                display: block;\n                                                                                width: 148px;\n                                                                                height: 68px;\n                                                                                opacity: 0;\n                                                                            }\n                                                                        </style>\n                                                                        <button class=\"open-wxapp-btn3\">\u6253\u5F00\u5C0F\u7A0B\u5E8F</button>\n                                                                    </template>\n                                                                </wx-open-launch-weapp>");
                    htmlStr += "<div class=\"item coupon\">\n                            <div class=\"icon\" style=\"background-image: url('".concat(prizelog.defaultImg, "');\"></div>\n                            <div class=\"info\">\n                                <div class=\"name\">").concat(prizelog.prizeName, "</div>\n                                <div class=\"source\">").concat(prizelog.remarks, "</div>\n                                <div class=\"time\">\n                                    ").concat(new Date(prizelog.ctime).Format("yyyy-MM-dd hh:mm"), "\n                                </div>\n                            </div>\n                            <div class=\"btn wxapp-btn\" data-id=\"").concat(prizelog.id, "\" data-type=\"").concat(couponType, "\">\n                                <p>\u53BB\u4F7F\u7528</p>\n                                ").concat(wxh5btn, "\n                            </div>\n                        </div>");
                }
                else if (prizelog.prizeType == 21) {
                    // 十全大奖，线下核销券（20公里内无门店才发货）
                    var btnText = '去领奖';
                    if (prizelog.address) {
                        btnText = '地址详情';
                        if (prizelog.expressName == '门店自提') {
                            btnText = '预约信息';
                        }
                        else if (prizelog.expressNo) {
                            btnText = '快递详情';
                        }
                    }
                    else if (!localStorage.latitude) {
                        btnText = '填写地址';
                    }
                    htmlStr += "<div class=\"item offline\">\n                                        <div class=\"icon\" style=\"background-image: url('".concat(prizelog.defaultImg, "');\"></div>\n                                        <div class=\"info\">\n                                            <div class=\"name\">").concat(prizelog.prizeName, "</div>\n                                            <div class=\"source\">").concat(prizelog.remarks, "</div>\n                                            <div class=\"time\">\n                                                ").concat(new Date(prizelog.ctime).Format("yyyy-MM-dd hh:mm"), "\n                                            </div>\n                                        </div>\n                                        <div class=\"btn \" data-id=\"").concat(prizelog.id, "\">\n                                            <p>").concat(btnText, "</p>\n                                        </div>\n                                    </div>");
                }
                else {
                    //实物
                    var btnText = '填地址';
                    if (prizelog.address) {
                        btnText = '地址详情';
                    }
                    if (prizelog.expressNo) {
                        btnText = '快递详情';
                    }
                    htmlStr += "<div class=\"item physical\">\n                            <div class=\"icon\" style=\"background-image: url('".concat(prizelog.defaultImg, "');\"></div>\n                            <div class=\"info\">\n                                <div class=\"name\">").concat(prizelog.prizeName, "</div>\n                                <div class=\"source\">").concat(prizelog.remarks, "</div>\n                                <div class=\"time\">\n                                    ").concat(new Date(prizelog.ctime).Format("yyyy-MM-dd hh:mm"), "\n                                </div>\n                            </div>\n                            <div class=\"btn \" data-id=\"").concat(prizelog.id, "\">\n                                <p>").concat(btnText, "</p>\n                            </div>\n                        </div>");
                }
            }
            if (!htmlStr) {
                htmlStr = "<div class=\"empty\">\n                        \u6682\u672A\u83B7\u5F97\u5956\u54C1\n                    </div>";
            }
            $('#mask-my-prize .scroll-y').html(htmlStr);
            bindAddressClick();
            callback && callback();
        });
        // }, true);
    };
    $('.show-mask[data-mask="my-prize"]').click(function () {
        if (userData.unionid) {
            getMyPrize();
        }
    });
    $('#mask-address .m-close').click(function () {
        $('#mask-address').hide();
    });
    var prizeLogID = 0;
    var choiceStoreID = 0;
    var hasStore = false;
    var storeList = [];
    var choiceStore = {};
    var curPrizeLog = null;
    var pcaData = ['430000', '430100', '430101'];
    //填写收货地址等按钮更新
    var bindAddressClick = function () {
        $('#mask-my-prize .scroll-y .coupon .btn').click(function () {
            var couponType = $(this).data('type');
            if (plat == 'wxapp') {
                wx.miniProgram.navigateTo({
                    url: "/activity/pages/myCoupon/myCoupon?type=".concat(couponType)
                });
            }
        });
        $('#mask-my-prize .scroll-y .offline .btn').click(function () {
            prizeLogID = $(this).data('id');
            prizeLogID = Number(prizeLogID);
            for (var i = 0; i < myPrizeLog.length; i++) {
                var prizelog = myPrizeLog[i];
                if (prizelog.id == prizeLogID) {
                    curPrizeLog = prizelog;
                    break;
                }
            }
            var btnText = '去领奖';
            if (curPrizeLog.address) {
                btnText = '地址详情';
                if (curPrizeLog.expressName == '门店自提') {
                    btnText = '预约信息';
                }
                else if (curPrizeLog.expressNo) {
                    btnText = '快递详情';
                }
            }
            switch (btnText) {
                case '去领奖':
                    $('#mask-choice-store').addClass('can-appointment');
                    if (hasStore) {
                        $('#mask-choice-store').show();
                        break;
                    }
                    if (localStorage.latitude) {
                        //有gps
                        globalLoading.show();
                        $.get(apiHost + '/out/2212sping/getlbxStoreList', {
                            Latitude: localStorage.latitude,
                            Longitude: localStorage.longitude
                        }, function (res) {
                            console.log(res);
                            if (res.data && res.data.data) {
                                // weui.alert('附近有门店');
                                $('#mask-choice-store').show();
                                initStore(res.data.data);
                            }
                            else {
                                // weui.alert('附近没有门店');
                                $("#inp-name").val('');
                                $("#inp-phone").val('');
                                $("#inp-pca").val('');
                                $("#inp-address").val('');
                                $('#mask-address').show();
                            }
                            globalLoading.hide();
                        });
                    }
                    else {
                        //没有gps
                        $("#inp-name").val('');
                        $("#inp-phone").val('');
                        $("#inp-pca").val('');
                        $("#inp-address").val('');
                        $('#mask-address').show();
                    }
                    break;
                case '预约信息':
                    if (plat == 'wxapp') {
                        $('#coupon-btn').hide();
                    }
                    else {
                        var couponType = 1;
                        var path = "activity/pages/myCoupon/myCoupon?type=".concat(couponType);
                        if (curPrizeLog.cardInfo) {
                            path = "activity/pages/xyxCouponDetail/xyxCouponDetail?pplnu=".concat(curPrizeLog.cardInfo.sendPplnu, "&ppnum=").concat(curPrizeLog.cardInfo.sendPpnum, "&memberId=").concat(game_user_info.memberId, "&memberNo=").concat(game_user_info.memberNo, "&memberPhone=").concat(game_user_info.mobilePhone, "&deptId=").concat(localStorage.shop_id);
                            console.log(curPrizeLog.cardInfo, path);
                        }
                        $('#coupon-btn').attr('path', path);
                        if (location.host.indexOf('lbxcn.com') >= 0) {
                            // env = '';
                        }
                        else {
                            $('#coupon-btn').attr('env-version', "trial");
                        }
                    }
                    $(".appointment-name").text(curPrizeLog.name);
                    $(".appointment-phone").text(curPrizeLog.phone);
                    $(".appointment-date").text(curPrizeLog.province);
                    $(".appointment-address").text(curPrizeLog.address);
                    $('#mask-appointmentinfo').show();
                    break;
                case '地址详情':
                case '快递详情':
                    //已经填过了，则预填一下
                    $("#inp-name").val(curPrizeLog.name);
                    $("#inp-phone").val(curPrizeLog.phone);
                    pcaData = getValueCodeArr(curPrizeLog.province, curPrizeLog.city, curPrizeLog.area);
                    $("#inp-pca").val(curPrizeLog.province + curPrizeLog.city + curPrizeLog.area);
                    $("#inp-address").val(curPrizeLog.address);
                    $(".user-name").text(curPrizeLog.name);
                    $(".user-phone").text(curPrizeLog.phone);
                    $(".user-address").text(curPrizeLog.province + curPrizeLog.city + curPrizeLog.area + curPrizeLog.address);
                    if (curPrizeLog.expressName && curPrizeLog.expressNo) {
                        $(".user-express").html(curPrizeLog.expressName + '<br />' + curPrizeLog.expressNo);
                        $('#mask-addressinfo .show-mask').hide();
                        $('#mask-addressinfo .pannel .m-close').css('left', '194px');
                    }
                    else {
                        $(".user-express").html('待发货');
                        if (new Date().valueOf() > new Date(curPrizeLog.ctime).valueOf() + 7 * 24 * 60 * 60 * 1000) {
                            $('#mask-addressinfo .show-mask').hide();
                            $('#mask-addressinfo .pannel .m-close').css('left', '194px');
                        }
                        else {
                            $('#mask-addressinfo .show-mask').show();
                            $('#mask-addressinfo .pannel .m-close').css('left', '40px');
                        }
                    }
                    $('#mask-addressinfo').show();
                    break;
                default:
                    break;
            }
        });
        $('#mask-my-prize .scroll-y .physical .btn').click(function () {
            prizeLogID = $(this).data('id');
            prizeLogID = Number(prizeLogID);
            for (var i = 0; i < myPrizeLog.length; i++) {
                var prizelog = myPrizeLog[i];
                if (prizelog.id == prizeLogID) {
                    curPrizeLog = prizelog;
                    break;
                }
            }
            // console.log(curPrizeLog);
            if (curPrizeLog.address) {
                //已经填过了，则预填一下
                $("#inp-name").val(curPrizeLog.name);
                $("#inp-phone").val(curPrizeLog.phone);
                pcaData = getValueCodeArr(curPrizeLog.province, curPrizeLog.city, curPrizeLog.area);
                $("#inp-pca").val(curPrizeLog.province + curPrizeLog.city + curPrizeLog.area);
                $("#inp-address").val(curPrizeLog.address);
                $(".user-name").text(curPrizeLog.name);
                $(".user-phone").text(curPrizeLog.phone);
                $(".user-address").text(curPrizeLog.province + curPrizeLog.city + curPrizeLog.area + curPrizeLog.address);
                console.log(curPrizeLog);
                if (curPrizeLog.expressName && curPrizeLog.expressNo) {
                    $(".user-express").html(curPrizeLog.expressName + '<br />' + curPrizeLog.expressNo);
                    $('#mask-addressinfo .show-mask').hide();
                    $('#mask-addressinfo .pannel .m-close').css('left', '194px');
                }
                else {
                    $(".user-express").html('待发货');
                    if (new Date().valueOf() > new Date(curPrizeLog.ctime).valueOf() + 7 * 24 * 60 * 60 * 1000) {
                        $('#mask-addressinfo .show-mask').hide();
                        $('#mask-addressinfo .pannel .m-close').css('left', '194px');
                    }
                    else {
                        $('#mask-addressinfo .show-mask').show();
                        $('#mask-addressinfo .pannel .m-close').css('left', '40px');
                    }
                }
                $('#mask-addressinfo').show();
            }
            else {
                $("#inp-name").val('');
                $("#inp-phone").val('');
                $("#inp-pca").val('');
                $("#inp-address").val('');
                $('#mask-address').show();
            }
        });
    };
    $('#mask-addressinfo .m-close,#mask-addressinfo .show-mask').click(function () {
        $('#mask-addressinfo').hide();
    });
    $('#mask-appointmentinfo .m-close').click(function () {
        $('#mask-appointmentinfo').hide();
    });
    $('#mask-appointmentinfo .btn-sr').click(function () {
        if (plat == 'wxapp') {
            var couponType = 1;
            var path = "activity/pages/myCoupon/myCoupon?type=".concat(couponType);
            if (curPrizeLog.cardInfo) {
                path = "activity/pages/xyxCouponDetail/xyxCouponDetail?pplnu=".concat(curPrizeLog.cardInfo.sendPplnu, "&ppnum=").concat(curPrizeLog.cardInfo.sendPpnum, "&memberId=").concat(game_user_info.memberId, "&memberNo=").concat(game_user_info.memberNo, "&memberPhone=").concat(game_user_info.mobilePhone, "&deptId=").concat(localStorage.shop_id);
                console.log(curPrizeLog.cardInfo, path);
            }
            wx.miniProgram.navigateTo({
                url: path
            });
        }
    });
    var initStore = function (list) {
        if (hasStore) {
            return;
        }
        hasStore = true;
        storeList = list;
        var htmlStr = '';
        for (var i = 0; i < list.length && i < 5; i++) {
            var element = list[i];
            var time = '';
            if (element.dateYyKs && element.dateYyJs) {
                time = "<div class=\"time\">".concat(element.dateYyKs, "-").concat(element.dateYyJs, "</div>");
            }
            htmlStr += "<div class=\"item\">\n                            <div class=\"name\">".concat(element.deptAbbreviation, "</div>\n                            ").concat(time, "\n                            <div class=\"phone\"><a href=\"tel:").concat(element.contactPhone, "\">").concat(element.contactPhone, "</a></div>\n                            <div class=\"location\">").concat(element.address, "</div>\n                            <img src=\"https://lbx-prod-yx-1302700033.cos.ap-guangzhou.myqcloud.com/image/k23.png\" data-shop_index=\"").concat(i, "\" data-shop_id=\"").concat(element.shop_id, "\" class=\"btn btn-appointment\" alt=\"\" srcset=\"\">\n                        </div>");
        }
        $('#mask-choice-store .scroll-y').html(htmlStr);
    };
    $('#mask-choice-store .scroll-y').click(function (e) {
        if (e.target.className.indexOf('btn-appointment') >= 0) {
            //是按钮
            var index = e.target.getAttribute('data-shop_index');
            choiceStoreID = e.target.getAttribute('data-shop_id');
            choiceStore = storeList[parseInt(index)];
            $("#appointment-address").val(choiceStore.deptName);
            $('#mask-appointment').show();
        }
    });
    $('#mask-appointment .date-picker').click(function () {
        // 级联picker
        weui.datePicker({
            start: new Date(),
            end: 2023,
            className: 'pca-picker',
            container: 'body',
            onChange: function (result) {
                // console.log(result)
                // pcaData = result;
                $('#appointment-date').val(result[0].value + '-' + result[1].value + '-' + result[2].value);
            },
            onConfirm: function (result) {
                // console.log(result)
                // pcaData = result;
                $('#appointment-date').val(result[0].value + '-' + result[1].value + '-' + result[2].value);
            },
            id: 'datePicker'
        });
    });
    $('#btn-appointment').click(function () {
        var name = $("#appointment-name").val();
        var phone = $("#appointment-phone").val();
        var date = $("#appointment-date").val();
        if (!name) {
            return weui.alert('请输入姓名');
        }
        if (!testTel(phone)) {
            return weui.alert('请输入准确的手机号');
        }
        if (!date) {
            return weui.alert('请选择预约时间');
        }
        globalLoading.show();
        $.post("".concat(apiHost, "/api/client/spring2026/prize/appointment"), {
            prizeLogID: prizeLogID,
            name: name,
            phone: phone,
            province: date,
            // city: choiceStoreID,
            expressNo: choiceStoreID,
            expressName: '门店自提',
            address: choiceStore.deptName,
        }, function (res) {
            globalLoading.hide();
            if (res.code == 1) {
                weui.alert('预约成功');
                needMyPrize = true;
                getMyPrize();
                $("#mask-appointment").hide();
                $("#mask-choice-store").hide();
            }
            else {
                weui.alert(res.message);
            }
        });
    });
    $('#mask-address .pca-picker').click(function () {
        // 级联picker
        weui.picker(cityDataV5, {
            className: 'pca-picker',
            container: 'body',
            defaultValue: pcaData,
            onChange: function (result) {
                // console.log(result)
                pcaData = result;
                $('#inp-pca').val(result[0].label + result[1].label + result[2].label);
            },
            onConfirm: function (result) {
                pcaData = result;
                $('#inp-pca').val(result[0].label + result[1].label + result[2].label);
            },
            id: 'cityPicker'
        });
    });
    $('#btn-submit').click(function () {
        if (new Date().valueOf() >
            new Date('2026/03/10 23:59:59').valueOf()) {
            return weui.alert('活动已结束一周，无法再修改收件地址');
        }
        needMyPrize = true;
        var name = $("#inp-name").val();
        var phone = $("#inp-phone").val();
        var pca = $("#inp-pca").val();
        var address = $("#inp-address").val();
        if (!name) {
            return weui.alert('请输入姓名');
        }
        if (!testTel(phone)) {
            return weui.alert('请输入准确的手机号');
        }
        if (!pca) {
            return weui.alert('请选择收货城市');
        }
        if (!address) {
            return weui.alert('请输入地址');
        }
        globalLoading.show();
        $.post("".concat(apiHost, "/api/client/spring2026/prize/editaddress"), {
            gameCode: gameCode,
            unionID: userData.unionid,
            prizeLogID: prizeLogID,
            name: name,
            phone: phone,
            province: getCodeValue(pcaData[0]),
            city: getCodeValue(pcaData[1]),
            area: getCodeValue(pcaData[2]),
            address: address,
        }, function (res) {
            globalLoading.hide();
            if (res.code == 1) {
                if (prizeLogID == 0) {
                    localStorage.saveAddress = 1;
                    weui.dialog({
                        title: '保存成功',
                        content: '当前排名不代表最终排名，奖品发放以最终结果为准',
                        className: 'custom-classname',
                        buttons: [{
                                label: '我知道了',
                                type: 'primary',
                                onClick: function () {
                                    $("#mask-address").hide();
                                }
                            }]
                    });
                }
                else {
                    weui.alert('保存成功');
                    needMyPrize = true;
                    getMyPrize();
                    $("#mask-address").hide();
                }
            }
            else {
                weui.alert(res.message);
            }
        });
    });
    return {
        fillRankAddress: function () {
            if (localStorage.userProvince && localStorage.userCity) {
                pcaData = [localStorage.userProvince, localStorage.userCity,
                    localStorage.userCity.substr(0, 4) + '01'];
            }
            //没获取过奖品
            getMyPrize(function () {
                if (rankPrizeLog) {
                    //已经填过了，则预填一下
                    var curPrizeLog_1 = rankPrizeLog;
                    $("#inp-name").val(curPrizeLog_1.name);
                    $("#inp-phone").val(curPrizeLog_1.phone);
                    pcaData = getValueCodeArr(curPrizeLog_1.province, curPrizeLog_1.city, curPrizeLog_1.area);
                    $("#inp-pca").val(curPrizeLog_1.province + curPrizeLog_1.city + curPrizeLog_1.area);
                    $("#inp-address").val(curPrizeLog_1.address);
                    console.log(rankPrizeLog);
                }
                prizeLogID = 0;
                $("#mask-address").show();
            });
        },
        initStore: initStore,
        getZoumadeng: getZoumadeng,
        refreshMyPrize: function () {
            needMyPrize = true;
            // getMyPrize();
        },
    };
})();
//品牌与埋点
var m_brand = (function () {
    $('#page-start .show-mask[data-mask="rule"]').click(function () {
        gdp('track', 'spring2023_game_rule', {
            game_source: localStorage.source,
            game_from_page: 'main'
        });
    });
    $('#page-start .show-mask[data-mask="rank"]').click(function () {
        gdp('track', 'spring2023_game_rank', {
            game_source: localStorage.source,
            game_from_page: 'main'
        });
    });
    $('#page-start .show-mask[data-mask="my-prize"]').click(function () {
        gdp('track', 'spring2023_game_myprize', {
            game_source: localStorage.source,
            game_from_page: 'main'
        });
    });
    // $('#mask-pictures .show-mask[data-mask="rule"]').click(() => {
    //     gdp('track', 'spring2023_game_rule', {
    //         game_source: localStorage.source,
    //         game_from_page: 'picture'
    //     });
    // })
    // $('#mask-package .show-mask[data-mask="pictures"]').click(() => {
    //     gdp('track', 'spring2023_game_picture', {
    //         game_source: localStorage.source,
    //     });
    // })
    // $('#mask-rank .show-mask[data-mask="my-prize"]').click(() => {
    //     gdp('track', 'spring2023_game_myprize', {
    //         game_source: localStorage.source,
    //         game_from_page: 'rank'
    //     });
    // })
    // $('#mask-package .show-mask[data-mask="my-prize"]').click(() => {
    //     gdp('track', 'spring2023_game_myprize', {
    //         game_source: localStorage.source,
    //         game_from_page: 'package'
    //     });
    // })
    // $('#page-game .show-mask[data-mask="my-prize"]').click(() => {
    //     gdp('track', 'spring2023_game_myprize', {
    //         game_source: localStorage.source,
    //         game_from_page: 'gaming'
    //     });
    // })
    // $('#mask-exchange-prize .show-mask[data-mask="my-prize"]').click(() => {
    //     gdp('track', 'spring2023_game_myprize', {
    //         game_source: localStorage.source,
    //         game_from_page: 'exchange'
    //     });
    // })
    // $('#mask-package .show-mask[data-mask="exchange-prize"]').click(() => {
    //     gdp('track', 'spring2023_game_exchange', {
    //         game_source: localStorage.source,
    //         game_from_page: 'package'
    //     });
    // })
    // $('#mask-package .show-mask[data-mask="upload"]').click(() => {
    //     gdp('track', 'spring2023_game_upload', {
    //         game_source: localStorage.source,
    //         game_from_page: 'package'
    //     });
    // })
    $('#mask-task #task-share .btn').click(function () {
        gdp('track', 'spring2023_game_share', {
            game_source: localStorage.source,
            game_from_page: 'task-share'
        });
    });
    $('#btn-goZhuanchang').on('touchstart', function () {
        gdp('track', 'spring2023_game_viewwxapp', {
            game_source: localStorage.source,
            game_from_page: 'recomend'
        });
    });
    $('#btn-goBuy').on('touchstart', function () {
        gdp('track', 'spring2023_game_viewwxapp', {
            game_source: localStorage.source,
            game_from_page: 'ad_main'
        });
    });
    $('#mask-task #task-buy .btn-area').on('touchstart', function () {
        gdp('track', 'spring2023_game_viewwxapp', {
            game_source: localStorage.source,
            game_from_page: 'task-buy'
        });
    });
    $('#mask-task #task-view .btn-area').on('touchstart', function () {
        gdp('track', 'spring2023_game_viewwxapp', {
            game_source: localStorage.source,
            game_from_page: 'task-view'
        });
    });
    $('#mask-task #task-video .btn-area').on('touchstart', function () {
        gdp('track', 'spring2023_game_viewwxapp', {
            game_source: localStorage.source,
            game_from_page: 'task-video'
        });
    });
    $('#mask-task #task-order .btn-area').on('touchstart', function () {
        gdp('track', 'spring2023_game_exchange', {
            game_source: localStorage.source,
            game_from_page: 'task-order'
        });
    });
    $('#mask-task #task-score .btn-area').on('touchstart', function () {
        gdp('track', 'spring2023_game_exchange', {
            game_source: localStorage.source,
            game_from_page: 'task-score'
        });
    });
    var brandList = [];
    return {
        init: function (list) {
            //广告位列表
            // console.log(list);
        },
        adview: function (cengshu) {
            return;
            var adIndex = cengshu % 3;
            console.log(adIndex);
            if (adIndex === 1 && cengshu < 8) {
                gdp('track', 'spring2023_game_adview', {
                    game_ad_code: '老百姓大药房',
                    game_ad_type: 1,
                });
            }
        }
    };
})();
//# sourceMappingURL=main.js.map