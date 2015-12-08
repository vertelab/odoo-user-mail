(function () {
'use strict';
var website = openerp.website;

website.if_dom_contains('div.o_website_info', function () {
    // automatically generate a menu from h1 and h2 tag in content
    var $container = $('body[data-target=".navspy"]');
    var ul = $('[data-id="info_sidebar"]', $container);
    var sub_li = null;
    var sub_ul = null;
    $("[id^=info_header_], [id^=info_]", $container).attr("id", "");
    $("h1, h2", $container).each(function() {
        var id;
        if(this.getAttribute('data-header') == 'true'){
            switch (this.tagName.toLowerCase()) {
                case "h1":
                    id = _.uniqueId('info_header_');
                    $(this.parentNode).attr('id',id);
                    sub_li = $("<li>").html('<a href="#'+id+'">'+$(this).text()+'</a>').appendTo(ul);
                    sub_ul = null;
                    break;
                case "h2":
                    id = _.uniqueId('info_');
                    if (sub_li) {
                        if (!sub_ul) {
                            sub_ul = $("<ul class='nav'>").appendTo(sub_li);
                        }
                        $(this.parentNode).attr('id',id);
                        $("<li>").html('<a href="#'+id+'">'+$(this).text()+'</a>').appendTo(sub_ul);
                    }
                    break;
                }
            }
        });
    });
}());
