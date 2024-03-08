from ..image_handlers import _ImageUpdateCommand


class _QemuImageCreate(_ImageUpdateCommand):
    """
    qemu-img create [--object OBJECTDEF] [-q] [-f FMT] [-b BACKING_FILE [-F BACKING_FMT]] [-u] [-o OPTIONS] FILENAME [SIZE]
    {"create": {}}
    {"create": {"images": [stg]}}

    """

    _UPDATE_ACTION = "create"

    @staticmethod
    def execute(image, arguments):
        image.spec["topology"]
        if params.get("create_with_dd") == "yes" and self.image_format == "raw":
            # maps K,M,G,T => (count, bs)
            human = {
                "K": (1, 1),
                "M": (1, 1024),
                "G": (1024, 1024),
                "T": (1024, 1048576),
            }
            if self.size[-1] in human:
                block_size = human[self.size[-1]][1]
                size = int(self.size[:-1]) * human[self.size[-1]][0]
            qemu_img_cmd = "dd if=/dev/zero of=%s count=%s bs=%sK" % (
                self.image_filename,
                size,
                block_size,
            )
        else:
            cmd_dict = {}
            cmd_dict["image_format"] = self.image_format
            if self.base_tag:
                # if base image has secret, use json representation
                base_key_secrets = self.encryption_config.base_key_secrets
                if self.base_tag in [
                    s.image_id for s in base_key_secrets
                ] or self._need_auth_info(self.base_tag):
                    base_params = params.object_params(self.base_tag)
                    cmd_dict["backing_file"] = "'%s'" % get_image_json(
                        self.base_tag, base_params, self.root_dir
                    )
                else:
                    cmd_dict["backing_file"] = self.base_image_filename
                cmd_dict["backing_format"] = self.base_format

            # secret objects of the backing images
            secret_objects = self._backing_access_secret_objects

            # secret object of the image itself
            if self._image_access_secret_object:
                secret_objects.extend(self._image_access_secret_object)

            image_secret_objects = self._secret_objects
            if image_secret_objects:
                secret_objects.extend(image_secret_objects)
            if secret_objects:
                cmd_dict["secret_object"] = " ".join(secret_objects)

            # tls creds objects of the backing images of the source
            tls_creds_objects = self._backing_access_tls_creds_objects

            # tls creds object of the source image itself
            if self._image_access_tls_creds_object:
                tls_creds_objects.append(self._image_access_tls_creds_object)

            if tls_creds_objects:
                cmd_dict["tls_creds_object"] = " ".join(tls_creds_objects)

            cmd_dict["image_filename"] = self.image_filename
            cmd_dict["image_size"] = self.size
            options = self._parse_options(params)
            if options:
                cmd_dict["options"] = ",".join(options)
            qemu_img_cmd = (
                self.image_cmd
                + " "
                + self._cmd_formatter.format(self.create_cmd, **cmd_dict)
            )

        if params.get("image_backend", "filesystem") == "filesystem":
            image_dirname = os.path.dirname(self.image_filename)
            if image_dirname and not os.path.isdir(image_dirname):
                e_msg = (
                    "Parent directory of the image file %s does "
                    "not exist" % self.image_filename
                )
                LOG.error(e_msg)
                LOG.error("This usually means a serious setup exceptions.")
                LOG.error(
                    "Please verify if your data dir contains the "
                    "expected directory structure"
                )
                LOG.error("Backing data dir: %s", data_dir.get_backing_data_dir())
                LOG.error("Directory structure:")
                for root, _, _ in os.walk(data_dir.get_backing_data_dir()):
                    LOG.error(root)

                LOG.warning(
                    "We'll try to proceed by creating the dir. "
                    "Other errors may ensue"
                )
                os.makedirs(image_dirname)

        msg = "Create image by command: %s" % qemu_img_cmd
        error_context.context(msg, LOG.info)
        cmd_result = process.run(
            qemu_img_cmd, shell=True, verbose=False, ignore_status=True
        )
        if cmd_result.exit_status != 0 and not ignore_errors:
            raise exceptions.TestError(
                "Failed to create image %s\n%s" % (self.image_filename, cmd_result)
            )
        pass
