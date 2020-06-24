//~ openerp.mail_extra = openerp.mail;
//~ openerp.mail = function (session) {
    //~ openerp.mail_extra(session);
openerp.mail_extra = function (session) {
    var _t = session.web._t,
       _lt = session.web._lt;

    var mail = session.mail;

    //~ openerp_mail_followers(session, mail);          // import mail_followers.js
    //~ openerp_FieldMany2ManyTagsEmail(session);       // import manyy2many_tags_email.js
    //~ openerp_announcement(session);

    
    mail.Wall.include({
    //~ mail.Wall = mail.Wall.extend({
        bind_events: function () {
            this._super();
            var self = this;
            console.log('is this thing on?');
            this.$(".oe_me_mark_as_read").click(function (event) { self.mark_all_read(); console.log(this); console.log(self) });
        },
        mark_all_read: function () {
            var self = this;
            alert('Mark All Mails As Read');
            console.log(self);
            
            var model = new session.web.Model("mail.message");
            model.call("message_mark_all_as_read", {context: new session.web.CompoundContext()}).then(function(result) {
                alert('All Mails Has Read');
                self.do_action(result);
                //~ self.$el.append("<div>Hello " + result["hello"] + "</div>");
                // will show "Hello world" to the user
            });
        }
    });
    //~ session.web.client_actions.add('mail.wall', 'session.mail.Wall');
};
