openerp.mail_extra = function (session) {
    var _t = session.web._t,
       _lt = session.web._lt;

    var mail = session.mail;


    
    mail.Wall.include({
        bind_events: function () {
            this._super();
            var self = this;
            console.log('is this thing on?');
            this.$(".oe_me_mark_as_read").click(function (event) { self.mark_all_read(); console.log(this); console.log(self) });
        },
        mark_all_read: function () {
            var self = this;
            console.log(self);
            
            var model = new session.web.Model("mail.message");
            model.call("message_mark_all_as_read", {context: new session.web.CompoundContext()}).then(function(result) {
                self.do_action(result);
            });
        }
    });
};
