import gtk


class TestForm(gtk.Window):

    def __init__(self):
        super(TestForm, self).__init__()

        self.set_title("Key test")
        self.set_size_request(200, 200)
        self.set_position(gtk.WIN_POS_CENTER)

        fixed = gtk.Fixed()

        entry = gtk.Entry()
        fixed.put(entry, 10, 10)

        entry.connect("key_press_event", self.on_key_press_event)

        self.connect("destroy", gtk.main_quit)
        self.add(fixed)
        self.show_all()

        # Clean the text file:
        input_file = open("/tmp/autotest-rv_input", "w")
        input_file.close()

    def on_key_press_event(self, widget, event):
        # Store caught keycodes into text file
        input_file = open("/tmp/autotest-rv_input", "a")
        input_file.write("{0} ".format(event.keyval))
        input_file.close()


if __name__ == "__main__":
    TestForm()
    gtk.main()
